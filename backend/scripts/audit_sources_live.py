#!/usr/bin/env python3
"""Live probe enabled sources and emit hardening suggestions (backend-only).

Purpose:
- validate DSL/runtime assumptions against real endpoints
- identify broken endpoints (404/timeout)
- suggest safe profile upgrades (API/PDF/SPA_HEADLESS) for future backfills
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
import psycopg
from psycopg.rows import dict_row


def _backend_imports():
    import sys
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from app.schemas.source_profile import SourceProfile  # type: ignore

    return SourceProfile


def _db_url() -> str:
    return (
        os.getenv("DATABASE_URL_SYNC")
        or os.getenv("RADAR_DB_URL_SYNC")
        or "postgresql://radar:radar_secret@localhost:5434/radar_news"
    )


def _select_url(policy: dict[str, Any]) -> str:
    endpoints = policy.get("endpoints") if isinstance(policy.get("endpoints"), dict) else {}
    strategy = str(policy.get("strategy") or "")
    if strategy in {"API", "SPA_API"}:
        return str(endpoints.get("api") or endpoints.get("latest") or endpoints.get("feed") or "")
    if strategy == "PDF":
        return str(endpoints.get("latest") or endpoints.get("feed") or endpoints.get("api") or "")
    return str(endpoints.get("feed") or endpoints.get("latest") or endpoints.get("api") or "")


def _content_family(content_type: str) -> str:
    ct = (content_type or "").lower()
    if "application/json" in ct or ct.endswith("+json"):
        return "json"
    if "pdf" in ct:
        return "pdf"
    if "html" in ct:
        return "html"
    if ct:
        return ct.split(";")[0].strip()
    return "unknown"


def _suggestions(policy: dict[str, Any], result: dict[str, Any]) -> list[str]:
    suggestions: list[str] = []
    strategy = str(policy.get("strategy") or "")
    url = str(result.get("url") or "")
    ct_family = str(result.get("content_family") or "")
    status = int(result.get("status_code") or 0)

    if status in {404, 410}:
        suggestions.append("BROKEN_ENDPOINT_404")
    if (
        strategy == "SPA_HEADLESS"
        and status == 403
        and not result.get("error_class")
    ):
        suggestions.append("HTTPX_PROBE_LIMITATION_SPA_HEADLESS")
        return suggestions
    if status == 401:
        suggestions.append("AUTH_REQUIRED_OR_BLOCKED")
    if status == 403:
        suggestions.append("FORBIDDEN_OR_BOT_BLOCK")
    if status == 429:
        suggestions.append("RATE_LIMITED")
    if result.get("error_class"):
        suggestions.append(f"ERROR_{result['error_class']}")

    if ct_family == "json" and strategy not in {"API", "SPA_API"}:
        suggestions.append("SUGGEST_STRATEGY_API")
    if ct_family == "pdf" and strategy != "PDF":
        suggestions.append("SUGGEST_STRATEGY_PDF")
    if "in.gov.br/leitura-digital" in url and strategy != "SPA_HEADLESS":
        suggestions.append("SUGGEST_SPA_HEADLESS_DOU")
    return suggestions


@dataclass
class SourceProbe:
    id: int
    name: str
    domain: str
    enabled: bool
    policy: dict[str, Any]


async def _probe_one(client: httpx.AsyncClient, src: SourceProbe, sem: asyncio.Semaphore) -> dict[str, Any]:
    url = _select_url(src.policy)
    strategy = str(src.policy.get("strategy") or "")
    pool = str(src.policy.get("pool") or "")
    headers = dict(src.policy.get("headers") or {})
    headers.setdefault("User-Agent", "RadarHardNews/1.0 (audit)")
    timeout = 15.0
    limits = src.policy.get("limits") if isinstance(src.policy.get("limits"), dict) else {}
    try:
        timeout = float(limits.get("timeout_seconds") or 15)
    except Exception:
        timeout = 15.0

    result: dict[str, Any] = {
        "id": src.id,
        "name": src.name,
        "domain": src.domain,
        "strategy": strategy,
        "pool": pool,
        "url": url,
        "status_code": None,
        "content_type": None,
        "content_family": None,
        "final_url": None,
        "latency_ms": None,
        "error_class": None,
        "suggestions": [],
    }
    if not url:
        result["error_class"] = "MissingEndpoint"
        result["suggestions"] = ["MISSING_ENDPOINT"]
        return result

    started = asyncio.get_running_loop().time()
    async with sem:
        try:
            async with client.stream("GET", url, headers=headers, timeout=timeout, follow_redirects=True) as resp:
                result["status_code"] = int(resp.status_code)
                result["content_type"] = resp.headers.get("content-type")
                result["content_family"] = _content_family(result["content_type"] or "")
                result["final_url"] = str(resp.url)
                # Read only a small prefix to avoid downloading huge pages/files.
                read = 0
                async for chunk in resp.aiter_bytes():
                    read += len(chunk)
                    if read >= 65536:
                        break
        except Exception as exc:
            result["error_class"] = type(exc).__name__
    result["latency_ms"] = int((asyncio.get_running_loop().time() - started) * 1000)
    result["suggestions"] = _suggestions(src.policy, result)
    return result


def _load_sources() -> list[SourceProbe]:
    SourceProfile = _backend_imports()
    rows: list[SourceProbe] = []
    with psycopg.connect(_db_url(), row_factory=dict_row) as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, name, domain, enabled, fetch_policy_json
                FROM sources
                WHERE enabled = TRUE
                ORDER BY id ASC
                """
            )
            for row in cur.fetchall():
                policy = dict(row.get("fetch_policy_json") or {})
                # Re-validate DSL for audit correctness; keep row but mark invalid if it fails.
                try:
                    SourceProfile(**policy)
                except Exception as exc:
                    policy = dict(policy)
                    policy["_audit_invalid_profile"] = str(exc)
                rows.append(
                    SourceProbe(
                        id=int(row["id"]),
                        name=str(row.get("name") or ""),
                        domain=str(row.get("domain") or ""),
                        enabled=bool(row.get("enabled")),
                        policy=policy,
                    )
                )
    return rows


def _dup_url_counts(sources: list[SourceProbe]) -> dict[str, int]:
    c: Counter[str] = Counter()
    for s in sources:
        url = _select_url(s.policy)
        if url:
            c[url] += 1
    return dict(c)


def _build_summary(results: list[dict[str, Any]], dup_counts: dict[str, int]) -> dict[str, Any]:
    by_status_class: Counter[str] = Counter()
    by_status_code: Counter[str] = Counter()
    by_content_family: Counter[str] = Counter()
    by_strategy: Counter[str] = Counter()
    suggestion_counts: Counter[str] = Counter()
    invalid_profiles = 0
    duplicate_url_active = 0
    probe_limitations = 0

    for r in results:
        code = r.get("status_code")
        suggestions = set(r.get("suggestions") or [])
        is_probe_limited = "HTTPX_PROBE_LIMITATION_SPA_HEADLESS" in suggestions
        if is_probe_limited:
            probe_limitations += 1
        if code is None:
            by_status_class["error"] += 1
        elif not is_probe_limited:
            by_status_code[str(code)] += 1
            by_status_class[f"{int(code)//100}xx"] += 1
        fam = str(r.get("content_family") or "unknown")
        by_content_family[fam] += 1
        by_strategy[str(r.get("strategy") or "unknown")] += 1
        for s in suggestions:
            suggestion_counts[str(s)] += 1
        if r.get("invalid_profile"):
            invalid_profiles += 1
        if dup_counts.get(str(r.get("url") or ""), 0) > 1:
            duplicate_url_active += 1

    top_issues = [r for r in results if r.get("suggestions")]
    top_issues = sorted(
        top_issues,
        key=lambda x: (len(x.get("suggestions") or []), -(x.get("status_code") or 0), x.get("id") or 0),
        reverse=True,
    )[:100]

    return {
        "sources_probed": len(results),
        "by_status_class": dict(by_status_class),
        "by_status_code": dict(by_status_code),
        "by_content_family": dict(by_content_family),
        "by_strategy": dict(by_strategy),
        "suggestion_counts": dict(suggestion_counts),
        "duplicate_url_active": duplicate_url_active,
        "invalid_profiles": invalid_profiles,
        "probe_limitations": probe_limitations,
        "top_issues": top_issues,
    }


async def run_audit(*, concurrency: int = 16) -> dict[str, Any]:
    sources = _load_sources()
    dup_counts = _dup_url_counts(sources)
    sem = asyncio.Semaphore(max(1, concurrency))
    limits = httpx.Limits(max_keepalive_connections=20, max_connections=max(50, concurrency * 3))
    timeout = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0)
    async with httpx.AsyncClient(limits=limits, timeout=timeout) as client:
        results = await asyncio.gather(*[_probe_one(client, src, sem) for src in sources])
    # Enrich with duplicate-url marker and invalid profile marker after probe.
    for src, r in zip(sources, results):
        if src.policy.get("_audit_invalid_profile"):
            r["invalid_profile"] = str(src.policy["_audit_invalid_profile"])
            r.setdefault("suggestions", []).append("INVALID_PROFILE_DSL")
        if dup_counts.get(r.get("url") or "", 0) > 1:
            r.setdefault("suggestions", []).append("DUPLICATE_ENDPOINT_ACTIVE")
    summary = _build_summary(results, dup_counts)
    return {
        "status": "ok",
        "db_url": _db_url(),
        "summary": summary,
        "results": results,
    }


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("artifacts") / "source_audit" / "latest.json",
        help="Write JSON report",
    )
    parser.add_argument("--summary-only", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    report = asyncio.run(run_audit(concurrency=max(1, args.concurrency)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    payload = {"status": "ok", "output": str(args.output), "summary": report["summary"]}
    if args.summary_only:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
