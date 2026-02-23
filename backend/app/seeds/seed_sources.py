"""Sync seed data for journalistic sources from legacy ~/news (Blueprint §6).

Goals:
- import all curated legacy sources
- preserve multiple endpoints from the same domain
- avoid duplicate crawlers (exact endpoint URL), including legacy alias rows
- keep SourceProfile DSL valid before persisting
"""
from __future__ import annotations

import asyncio
import importlib.util
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select

from app.db import async_session_factory
from app.models.source import Source
from app.schemas.source_profile import SourceProfile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LEGACY_YAML_PATH = Path("/home/diego/news/bootstrap/config/sources.yaml")
INTERNAL_YAML_PATH = Path("/app/sources_legacy.yaml")
MVP_DEFERRED_SOURCE_IDS = {"dou_oficial", "tcu_acordaos"}


def _load_convert_module():
    try:
        import convert_sources  # type: ignore

        return convert_sources
    except Exception:
        # Fallback when running file directly and /app root is not in sys.path.
        root = Path(__file__).resolve().parents[2]
        script_path = root / "convert_sources.py"
        spec = importlib.util.spec_from_file_location("convert_sources", script_path)
        if not spec or not spec.loader:
            raise RuntimeError(f"Cannot load convert_sources from {script_path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module


def _choose_legacy_path() -> Path:
    if LEGACY_YAML_PATH.exists():
        return LEGACY_YAML_PATH
    if INTERNAL_YAML_PATH.exists():
        return INTERNAL_YAML_PATH
    raise FileNotFoundError(
        f"Legacy sources YAML not found at {LEGACY_YAML_PATH} nor {INTERNAL_YAML_PATH}"
    )


def _signature_from_policy(policy: dict[str, Any] | None) -> tuple[str, str]:
    data = dict(policy or {})
    source_id = str(data.get("source_id") or "").strip()
    endpoints = data.get("endpoints")
    endpoint_url = ""
    if isinstance(endpoints, dict):
        endpoint_url = str(next(iter(endpoints.values()), "") or "").strip()
    return source_id, endpoint_url


def _endpoint_url_from_policy(policy: dict[str, Any] | None) -> str:
    return _signature_from_policy(policy)[1]


def _source_id_from_policy(policy: dict[str, Any] | None) -> str:
    return _signature_from_policy(policy)[0]


def _profile_quality_score(src: Source, *, converted_signature_set: set[tuple[str, str]]) -> tuple[int, int, int]:
    """Higher tuple wins.

    Prioritize rows that match converted signatures from ~/news, then richer DSLs,
    then cleaner source_id formatting.
    """
    policy = dict(src.fetch_policy_json or {})
    sig = _signature_from_policy(policy)
    score = 0
    if sig in converted_signature_set:
        score += 100
    if policy.get("lang"):
        score += 5
    if policy.get("is_official") is True:
        score += 5
    if isinstance(policy.get("headers"), dict) and policy.get("headers"):
        score += 5
    if isinstance(policy.get("observability"), dict) and policy.get("observability"):
        score += 5
    if isinstance(policy.get("limits"), dict):
        limits = policy.get("limits") or {}
        score += min(len(limits), 4)
    if isinstance(policy.get("metadata"), dict):
        score += min(len(policy.get("metadata") or {}), 8)
    source_id = str(policy.get("source_id") or "")
    if source_id and "___" not in source_id:
        score += 3
    # Prefer enabled rows slightly, and newer rows (higher id) after quality tie.
    return (
        score + (1 if src.enabled else 0),
        score,
        int(src.id or 0),
    )


@dataclass
class SyncStats:
    inserted: int = 0
    updated: int = 0
    duplicates_disabled: int = 0
    duplicate_endpoints_disabled: int = 0
    normalized_existing: int = 0
    skipped_invalid: int = 0
    legacy_total: int = 0
    converted_total: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "duplicates_disabled": self.duplicates_disabled,
            "duplicate_endpoints_disabled": self.duplicate_endpoints_disabled,
            "normalized_existing": self.normalized_existing,
            "skipped_invalid": self.skipped_invalid,
            "legacy_total": self.legacy_total,
            "converted_total": self.converted_total,
        }


def _enrich_existing_policy(src: Source, conv) -> tuple[dict[str, Any], bool]:
    """Best-effort normalization of legacy/manual rows already stored in DB."""
    policy = dict(src.fetch_policy_json or {})
    original = dict(policy)
    endpoints = policy.get("endpoints") if isinstance(policy.get("endpoints"), dict) else {}
    endpoint_url = str(next(iter((endpoints or {}).values()), "") or "").strip()

    source_id = str(policy.get("source_id") or "").strip() or conv.slugify_source_id(src.name)
    source_domain = str(policy.get("source_domain") or "").strip() or str(src.domain or "")
    strategy = str(policy.get("strategy") or "").strip() or conv.infer_strategy(None, endpoint_url)
    pool = str(policy.get("pool") or "").strip() or conv.infer_pool(strategy)
    endpoint_key = conv.endpoint_key_for_strategy(strategy)

    # Re-map endpoint key only when endpoint exists and key is missing/incorrect for strategy.
    if endpoint_url:
        strategy_endpoints = dict(endpoints or {})
        if endpoint_key not in strategy_endpoints or len(strategy_endpoints) != 1:
            strategy_endpoints = {endpoint_key: endpoint_url}
        endpoints = strategy_endpoints

    policy["source_id"] = source_id
    policy["source_domain"] = source_domain
    policy["tier"] = int(src.tier or policy.get("tier") or 3)
    policy["is_official"] = bool(src.is_official)
    policy["lang"] = str(policy.get("lang") or getattr(src, "lang", "pt-BR") or "pt-BR")
    policy["strategy"] = strategy
    policy["pool"] = pool
    if endpoints:
        policy["endpoints"] = endpoints
    policy.setdefault("headers", {"User-Agent": conv.INSTITUTIONAL_UA})
    policy.setdefault("cadence", conv.cadence_for_tier(int(policy["tier"])))
    policy.setdefault(
        "limits",
        {
            "rate_limit_req_per_min": 10,
            "concurrency_per_domain": 1,
            "timeout_seconds": 30,
            "max_bytes": 5_000_000,
        },
    )
    policy.setdefault(
        "observability",
        {
            "starvation_window_hours": 24,
            "yield_keys": ["anchors_count", "evidence_score"],
            "baseline_rolling": True,
            "calendar_profile": "business_hours_br",
        },
    )
    policy.setdefault("metadata", {})

    policy = conv.apply_profile_overrides(
        source_id=source_id,
        name=str(src.name or ""),
        domain=str(src.domain or ""),
        url=endpoint_url,
        policy=policy,
    )

    # Final pool correction if strategy changed by override.
    expected_pool = conv.infer_pool(str(policy.get("strategy") or strategy))
    if str(policy.get("pool") or "") not in {"FAST_POOL", "HEAVY_RENDER_POOL", "DEEP_EXTRACT_POOL"}:
        policy["pool"] = expected_pool
    elif str(policy.get("strategy")) in {"SPA_HEADLESS", "SPA_API", "PDF"}:
        policy["pool"] = expected_pool

    # Validate; if invalid due contract specifics, keep original row unchanged.
    SourceProfile(**policy)
    changed = policy != original
    return policy, changed


async def sync_sources(*, disable_exact_duplicates: bool = True) -> SyncStats:
    conv = _load_convert_module()
    path = _choose_legacy_path()

    legacy_rows = conv.load_legacy_sources(path)
    converted = conv.convert_legacy_sources(legacy_rows)
    stats = SyncStats(legacy_total=len(legacy_rows), converted_total=len(converted))
    converted_signature_set = {
        _signature_from_policy((item.get("fetch_policy_json") or {}))
        for item in converted
        if isinstance(item, dict)
    }

    validation_errors = conv.validate_converted_profiles(converted)
    if validation_errors:
        logger.error("Converted legacy sources failed SourceProfile validation (%s errors)", len(validation_errors))
        for err in validation_errors[:20]:
            logger.error(" - %s", err)
        # Fail fast: do not persist invalid source profiles.
        raise RuntimeError(f"SourceProfile validation failed for {len(validation_errors)} converted sources")

    async with async_session_factory() as session:
        result = await session.execute(select(Source).order_by(Source.id.asc()))
        existing_rows = list(result.scalars().all())

        # Normalize historical/manual rows to current DSL before dedupe/upsert.
        for src in existing_rows:
            try:
                new_policy, changed = _enrich_existing_policy(src, conv)
            except Exception as exc:
                logger.warning("Skipping normalization for source id=%s (%s): %s", src.id, src.name, exc)
                continue
            if _source_id_from_policy(new_policy) in MVP_DEFERRED_SOURCE_IDS and src.enabled:
                src.enabled = False
            if changed:
                src.fetch_policy_json = new_policy
                stats.normalized_existing += 1

        by_signature: dict[tuple[str, str], list[Source]] = {}
        for src in existing_rows:
            sig = _signature_from_policy(src.fetch_policy_json)
            by_signature.setdefault(sig, []).append(src)

        if disable_exact_duplicates:
            for sig, rows in by_signature.items():
                if not sig[0] or not sig[1] or len(rows) <= 1:
                    continue
                keeper = rows[0]
                for dup in rows[1:]:
                    if dup.enabled:
                        dup.enabled = False
                        stats.duplicates_disabled += 1
                # Keep first row enabled unless user manually disabled it.
                logger.debug("Deduped sources signature %s keeping id=%s", sig, keeper.id)

        # Refresh signature index after duplicate normalization.
        by_signature = {}
        for src in existing_rows:
            sig = _signature_from_policy(src.fetch_policy_json)
            by_signature.setdefault(sig, []).append(src)

        for item in converted:
            policy = item.get("fetch_policy_json") or {}
            sig = _signature_from_policy(policy)
            if not sig[0] or not sig[1]:
                stats.skipped_invalid += 1
                continue

            existing = by_signature.get(sig, [])
            if existing:
                src = existing[0]
                src.domain = str(item.get("domain") or src.domain)
                src.name = str(item.get("name") or src.name)
                src.tier = int(item.get("tier") or src.tier)
                src.is_official = bool(item.get("is_official"))
                # Respect MVP deferrals; otherwise keep manual enabled/disabled decisions.
                if _source_id_from_policy(policy) in MVP_DEFERRED_SOURCE_IDS:
                    src.enabled = False
                src.fetch_policy_json = policy
                stats.updated += 1
                continue

            src = Source(
                domain=str(item["domain"]),
                name=str(item["name"]),
                tier=int(item["tier"]),
                is_official=bool(item["is_official"]),
                fetch_policy_json=policy,
                enabled=_source_id_from_policy(policy) not in MVP_DEFERRED_SOURCE_IDS,
            )
            session.add(src)
            existing_rows.append(src)
            by_signature.setdefault(sig, []).append(src)
            stats.inserted += 1

        # Deduplicate by exact endpoint URL across legacy aliases (e.g., old source_id variants).
        by_endpoint: dict[str, list[Source]] = {}
        for src in existing_rows:
            endpoint_url = _endpoint_url_from_policy(src.fetch_policy_json)
            if endpoint_url:
                by_endpoint.setdefault(endpoint_url, []).append(src)
        for endpoint_url, rows in by_endpoint.items():
            if len(rows) <= 1:
                continue
            keeper = sorted(
                rows,
                key=lambda s: _profile_quality_score(s, converted_signature_set=converted_signature_set),
                reverse=True,
            )[0]
            for dup in rows:
                if dup.id == keeper.id:
                    continue
                if dup.enabled:
                    dup.enabled = False
                    stats.duplicate_endpoints_disabled += 1

        await session.commit()

    logger.info("Source sync completed: %s", stats.as_dict())
    return stats


async def seed_sources():
    """Backward-compatible entrypoint used elsewhere in the repo."""
    return await sync_sources()


def _summarize_db_counts() -> dict[str, int]:
    # Lightweight sync summary helper for CLI logging; executed sync-style via psycopg if available.
    try:
        import psycopg  # type: ignore
        from app.config import settings

        dsn = str(getattr(settings, "DATABASE_URL_SYNC", "") or "")
        if not dsn:
            return {}
        with psycopg.connect(dsn) as conn:
            with conn.cursor() as cur:
                cur.execute("select count(*) from sources")
                total = int(cur.fetchone()[0])
                cur.execute("select count(distinct domain) from sources")
                distinct_domains = int(cur.fetchone()[0])
                return {"sources_total": total, "distinct_domains": distinct_domains}
    except Exception:
        return {}


if __name__ == "__main__":
    stats = asyncio.run(sync_sources())
    logger.info("Seed/sync stats: %s", stats.as_dict())
    counts = _summarize_db_counts()
    if counts:
        logger.info("DB counts after sync: %s", counts)
