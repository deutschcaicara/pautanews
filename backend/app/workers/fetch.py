"""Unified fetcher worker — handles RSS, HTML, and API strategies.

Implements Blueprint §9.1 and §13.
"""
from __future__ import annotations

import base64
import logging
import hashlib
import httpx
import socket
import ipaddress
import asyncio
from datetime import datetime, timezone
from typing import Any, Dict
from urllib.parse import urlparse

from app.celery_app import celery
from app.db import async_session_factory
from app.metrics import FETCH_ATTEMPTS_TOTAL, FETCH_LATENCY_SECONDS
from app.models.fetch_attempt import FetchAttempt
from app.models.snapshot import Snapshot
from app.schemas.source_profile import SourceProfile, StrategyType, PoolType
from app.workers.headless import fetch_headless

logger = logging.getLogger(__name__)

INSTITUTIONAL_UA = "RadarHardNews/1.0 (Institutional; newsroom monitoring)"
_redis_client = None


def _is_private_or_local_ip(value: str) -> bool:
    try:
        ip_obj = ipaddress.ip_address(value)
    except ValueError:
        return False
    return any(
        (
            ip_obj.is_private,
            ip_obj.is_loopback,
            ip_obj.is_link_local,
            ip_obj.is_multicast,
            ip_obj.is_unspecified,
            ip_obj.is_reserved,
        )
    )


def is_ssrf_safe(url: str) -> bool:
    """Check if URL uses http(s) and resolves only to public IPs (IPv4/IPv6)."""
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname or parsed.scheme not in {"http", "https"}:
            return False
        if hostname in {"localhost"} or hostname.endswith(".local"):
            return False
        if _is_private_or_local_ip(hostname):
            return False

        results = socket.getaddrinfo(hostname, None)
        for result in results:
            address = str(result[4][0] or "").strip()
            if address and _is_private_or_local_ip(address):
                return False
        return True
    except Exception as e:
        logger.error(f"SSRF check failed for {url}: {e}")
        return False


def _get_redis():
    global _redis_client
    if _redis_client is not None:
        return _redis_client
    try:
        import redis  # type: ignore
        from app.config import settings

        _redis_client = redis.Redis.from_url(settings.REDIS_URL, decode_responses=True)
    except Exception:
        _redis_client = None
    return _redis_client


def _rate_limit_key(source_pk: int, minute_bucket: str) -> str:
    return f"radar:rl:source:{source_pk}:{minute_bucket}"


async def _preflight_limits(profile: SourceProfile, url: str) -> str | None:
    """Return error class when blocked by rate-limit/circuit-breaker; else None."""
    source_pk = profile.id
    if source_pk is None:
        return "MissingSourceId"
    r = _get_redis()
    if r is None:
        return None
    try:
        now = datetime.now(timezone.utc)
        # Circuit breaker (simple): skip if source is in cooldown.
        if r.get(f"radar:cb:source:{source_pk}:open"):
            return "CircuitOpen"

        # Per-source rate limit per minute.
        bucket = now.strftime("%Y%m%d%H%M")
        rl_key = _rate_limit_key(source_pk, bucket)
        count = r.incr(rl_key)
        if count == 1:
            r.expire(rl_key, 90)
        if count > int(profile.limits.rate_limit_req_per_min):
            return "RateLimited"

        # Best-effort per-domain concurrency guard.
        hostname = (urlparse(url).hostname or "").lower()
        if hostname:
            ckey = f"radar:concurrency:{hostname}"
            current = r.incr(ckey)
            if current == 1:
                r.expire(ckey, max(5, int(profile.limits.timeout_seconds) + 5))
            if current > int(profile.limits.concurrency_per_domain):
                r.decr(ckey)
                return "DomainConcurrencyLimited"
        return None
    except Exception as exc:
        logger.warning("Fetch limit preflight failed for %s: %s", profile.source_id, exc)
        return None


def _release_domain_concurrency(url: str) -> None:
    r = _get_redis()
    if r is None:
        return
    hostname = (urlparse(url).hostname or "").lower()
    if not hostname:
        return
    ckey = f"radar:concurrency:{hostname}"
    try:
        r.decr(ckey)
    except Exception:
        return


def _record_circuit_result(profile: SourceProfile, success: bool) -> None:
    source_pk = profile.id
    if source_pk is None:
        return
    r = _get_redis()
    if r is None:
        return
    fail_key = f"radar:cb:source:{source_pk}:fails"
    open_key = f"radar:cb:source:{source_pk}:open"
    try:
        if success:
            r.delete(fail_key)
            r.delete(open_key)
            return
        fails = r.incr(fail_key)
        r.expire(fail_key, 300)
        if fails >= 5:
            r.setex(open_key, 120, "1")
    except Exception:
        return


def _select_fetch_url(profile: SourceProfile) -> str | None:
    if profile.strategy in {StrategyType.SPA_API, StrategyType.API}:
        return profile.endpoints.get("api") or profile.endpoints.get("latest") or profile.endpoints.get("feed")
    if profile.strategy == StrategyType.PDF:
        return profile.endpoints.get("latest") or profile.endpoints.get("feed") or profile.endpoints.get("api")
    return profile.endpoints.get("feed") or profile.endpoints.get("latest") or profile.endpoints.get("api")


def _api_request_overrides(profile: SourceProfile) -> dict[str, Any]:
    if profile.strategy not in {StrategyType.API, StrategyType.SPA_API}:
        return {}
    md = profile.metadata if isinstance(profile.metadata, dict) else {}
    cfg = md.get("spa_api_request") or md.get("api_request") or {}
    return cfg if isinstance(cfg, dict) else {}


def _prepare_request_spec(profile: SourceProfile, base_headers: dict[str, str]) -> dict[str, Any]:
    url = _select_fetch_url(profile)
    method = "GET"
    params = None
    json_body = None
    data_body = None
    headers = dict(base_headers)
    cfg = _api_request_overrides(profile)
    if cfg:
        url = str(cfg.get("url") or url) if (cfg.get("url") or url) else None
        method = str(cfg.get("method") or "GET").upper()
        if method not in {"GET", "POST"}:
            method = "GET"
        params = cfg.get("params") if isinstance(cfg.get("params"), dict) else None
        json_body = cfg.get("json") if isinstance(cfg.get("json"), (dict, list)) else None
        data_body = cfg.get("data") if isinstance(cfg.get("data"), (dict, str)) else None
        extra_headers = cfg.get("headers") if isinstance(cfg.get("headers"), dict) else None
        if extra_headers:
            headers.update({str(k): str(v) for k, v in extra_headers.items()})
    return {
        "url": url,
        "method": method,
        "params": params,
        "json": json_body,
        "data": data_body,
        "headers": headers,
    }

@celery.task(name="app.workers.fetch.run_fetch", bind=True, max_retries=3)
def run_fetch(self, profile_dict: Dict[str, Any]):
    """Entry point for all fetch jobs. Runs as a sync Celery task."""
    profile = SourceProfile(**profile_dict)
    logger.info(f"Starting fetch for {profile.source_id}")

    try:
        asyncio.run(_async_run_fetch(profile))
    except Exception as exc:
        logger.error(f"Fetch failed for {profile.source_id}: {exc}")
        self.retry(exc=exc, countdown=60)

async def _async_run_fetch(profile: SourceProfile):
    """Async implementation of the robust fetcher."""
    url = _select_fetch_url(profile)
    if not url:
        logger.warning(f"No URL found for {profile.source_id}")
        return

    # 1. SSRF Guard (Blueprint §2)
    if not is_ssrf_safe(url):
        logger.error(f"SSRF violation blocked: {url}")
        return
    preflight_block = await _preflight_limits(profile, url)
    if preflight_block:
        logger.warning("Fetch blocked for %s: %s", profile.source_id, preflight_block)
        # Persist blocked attempt for observability.
        source_pk = profile.id
        if source_pk is not None:
            async with async_session_factory() as session:
                session.add(
                    FetchAttempt(
                        source_id=source_pk,
                        url=url,
                        status_code=0,
                        error_class=preflight_block,
                        latency_ms=0,
                        bytes=0,
                        pool=profile.pool.value,
                        snapshot_hash=None,
                    )
                )
                await session.commit()
        FETCH_ATTEMPTS_TOTAL.labels(
            source_id=str(profile.source_id),
            strategy=profile.strategy.value,
            pool=profile.pool.value,
            status_class="blocked",
            error_class=preflight_block,
        ).inc()
        return

    # 2. Prepare ETag/IMS headers
    headers = profile.headers.copy() if profile.headers else {}
    headers.setdefault("User-Agent", INSTITUTIONAL_UA)
    last_etag = None
    last_modified = None
    
    async with async_session_factory() as session:
        from sqlalchemy import select, desc
        # Find latest snapshot for this URL
        stmt = select(Snapshot).where(Snapshot.url == url).order_by(desc(Snapshot.fetched_at)).limit(1)
        result = await session.execute(stmt)
        last_snap = result.scalar()
        
        if last_snap and last_snap.headers_json:
            last_etag = last_snap.headers_json.get("etag") or last_snap.headers_json.get("ETag")
            last_modified = last_snap.headers_json.get("last-modified") or last_snap.headers_json.get("Last-Modified")
            
            if last_etag:
                headers["If-None-Match"] = last_etag
            if last_modified:
                headers["If-Modified-Since"] = last_modified

    request_spec = _prepare_request_spec(profile, headers)
    url = request_spec.get("url") or url
    headers = request_spec["headers"]

    # 3. Fetch strategy execution
    resp: httpx.Response | None = None
    latency_ms = 0
    status_code = 0
    body = ""
    body_bytes_len = 0
    error_class = None
    payload_kind = "text"
    raw_payload_bytes: bytes | None = None

    try:
        if profile.strategy == StrategyType.SPA_HEADLESS:
            try:
                started = datetime.now(timezone.utc)
                body = await fetch_headless(profile, url)
                raw_payload_bytes = body.encode("utf-8", errors="ignore")
                body_bytes_len = len(raw_payload_bytes)
                latency_ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
                status_code = 200
                if body_bytes_len > profile.limits.max_bytes:
                    error_class = "MaxBytesExceeded"
                    body = ""
                    body_bytes_len = 0
            except Exception as e:
                logger.error(f"Headless fetch exception for {profile.source_id}: {e}")
                error_class = type(e).__name__
        else:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=profile.limits.timeout_seconds,
                follow_redirects=True,
            ) as client:
                try:
                    if request_spec["method"] == "POST":
                        resp = await client.post(
                            url,
                            params=request_spec.get("params"),
                            json=request_spec.get("json"),
                            data=request_spec.get("data"),
                        )
                    else:
                        resp = await client.get(
                            url,
                            params=request_spec.get("params"),
                        )
                    latency_ms = int(resp.elapsed.total_seconds() * 1000)
                    status_code = resp.status_code
                    
                    if resp.status_code == 304:
                        logger.info(f"Not modified (304) for {profile.source_id}")
                    else:
                        resp.raise_for_status()
                        content_length = int(resp.headers.get("content-length", "0") or 0)
                        if content_length and content_length > profile.limits.max_bytes:
                            error_class = "MaxBytesExceeded"
                            logger.warning(
                                "Max bytes exceeded by header for %s: %s > %s",
                                profile.source_id,
                                content_length,
                                profile.limits.max_bytes,
                            )
                        else:
                            raw_bytes = resp.content
                            body_bytes_len = len(raw_bytes)
                            if body_bytes_len > profile.limits.max_bytes:
                                error_class = "MaxBytesExceeded"
                                logger.warning(
                                    "Max bytes exceeded after download for %s: %s > %s",
                                    profile.source_id,
                                    body_bytes_len,
                                    profile.limits.max_bytes,
                                )
                            else:
                                raw_payload_bytes = raw_bytes
                                if profile.strategy == StrategyType.PDF:
                                    payload_kind = "pdf_base64"
                                    body = base64.b64encode(raw_bytes).decode("ascii")
                                else:
                                    body = resp.text
                    
                except httpx.HTTPStatusError as e:
                    logger.error(f"HTTP error {e.response.status_code} for {profile.source_id}")
                    status_code = e.response.status_code
                    error_class = "HTTPStatusError"
                except Exception as e:
                    logger.error(f"Fetch exception for {profile.source_id}: {e}")
                    error_class = type(e).__name__
    finally:
        _release_domain_concurrency(url)
            
    # 4. Persistence (Snapshot & FetchAttempt)
    if raw_payload_bytes is None and body:
        raw_payload_bytes = body.encode()
    content_hash = hashlib.sha256(raw_payload_bytes).hexdigest() if raw_payload_bytes else None
    computed_snapshot_hash = hashlib.sha256(f"{url}{content_hash}".encode()).hexdigest() if content_hash else None
    source_pk = profile.id
    if source_pk is None:
        logger.error("SourceProfile missing database id for %s", profile.source_id)
        return

    async with async_session_factory() as session:
        attempt = FetchAttempt(
            source_id=source_pk,
            url=url,
            status_code=status_code,
            error_class=error_class,
            latency_ms=latency_ms,
            bytes=body_bytes_len or (len(raw_payload_bytes) if raw_payload_bytes else (len(body) if body else 0)),
            pool=profile.pool.value,
            snapshot_hash=computed_snapshot_hash if (body and status_code == 200) else None,
        )
        session.add(attempt)

        if body and status_code == 200:
            # Check if this content is identical to the last one (if 304 failed/not supported)
            if last_snap and last_snap.content_hash == content_hash:
                logger.info(f"Content identical for {profile.source_id}, skipping extraction.")
            else:
                # Save snapshot
                snap = Snapshot(
                    url=url,
                    headers_json=dict(resp.headers) if resp else None,
                    body_ref=None,  # Local Storage not implem yet
                    content_hash=content_hash,
                    snapshot_hash=computed_snapshot_hash,
                )
                session.add(snap)
                await session.flush()  # Get snap.id

                # 5. Trigger Extraction (M3.2)
                target_extract_queue = "extract_fast"
                if profile.pool == PoolType.DEEP_EXTRACT_POOL or profile.strategy == StrategyType.PDF:
                    target_extract_queue = "extract_deep"
                fetch_meta = {
                    "snapshot_id": snap.id,
                    "source_url": url,
                    "response_headers": (dict(resp.headers) if resp else None),
                    "status_code": status_code,
                    "payload_kind": payload_kind,
                }
                celery.send_task(
                    "app.workers.extract.run_extraction",
                    args=[profile.model_dump(), body, content_hash, payload_kind, fetch_meta],
                    queue=target_extract_queue,
                    routing_key=target_extract_queue,
                )

        await session.commit()

    status_class = (
        "2xx" if 200 <= status_code < 300 else
        "3xx" if 300 <= status_code < 400 else
        "4xx" if 400 <= status_code < 500 else
        "5xx" if 500 <= status_code < 600 else
        "other"
    )
    FETCH_ATTEMPTS_TOTAL.labels(
        source_id=str(profile.source_id),
        strategy=profile.strategy.value,
        pool=profile.pool.value,
        status_class=status_class,
        error_class=(error_class or "NONE"),
    ).inc()
    FETCH_LATENCY_SECONDS.labels(
        strategy=profile.strategy.value,
        pool=profile.pool.value,
    ).observe(max(latency_ms, 0) / 1000.0)
    _record_circuit_result(profile, success=(status_code in (200, 304) and not error_class))
