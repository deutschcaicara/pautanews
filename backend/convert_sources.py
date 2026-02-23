#!/usr/bin/env python3
"""Convert legacy ~/news sources.yaml into backend Source seed rows + validate DSL."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import urlparse
from typing import Any

import yaml


DEFAULT_LEGACY_SOURCES_PATH = Path("/home/diego/news/bootstrap/config/sources.yaml")
INSTITUTIONAL_UA = "RadarHardNews/1.0 (Institutional; newsroom monitoring)"
PRIORITY_MAP = {"S0": 1, "S1": 2, "S2": 3}
TYPE_MAP = {"rss": "RSS", "watch": "HTML"}


def slugify_source_id(name: str) -> str:
    text = re.sub(r"[^a-zA-Z0-9]+", "_", (name or "").strip().lower())
    text = re.sub(r"_+", "_", text).strip("_")
    return text or "source"


def infer_strategy(stype: str | None, url: str | None) -> str:
    url_text = str(url or "").lower()
    if url_text.endswith(".pdf") or ".pdf?" in url_text:
        return "PDF"
    if any(token in url_text for token in ("/api/", "/rest/", "api.", "/graphql")):
        return "API"
    if any(token in url_text for token in ("leitura-digital",)):
        return "SPA_HEADLESS"
    return TYPE_MAP.get(str(stype or "").strip().lower(), "HTML")


def infer_pool(strategy: str) -> str:
    if strategy in {"SPA_API", "SPA_HEADLESS"}:
        return "HEAVY_RENDER_POOL"
    if strategy == "PDF":
        return "DEEP_EXTRACT_POOL"
    return "FAST_POOL"


def infer_is_official(domain: str, source_class: str | None = None) -> bool:
    return bool(
        ".gov.br" in domain
        or ".leg.br" in domain
        or ".jus.br" in domain
        or source_class == "primary"
    )


def _safe_taxonomy(name: str, url: str) -> tuple[str | None, str | None]:
    try:
        backend_dir = Path(__file__).resolve().parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        from app.core.taxonomy import infer_source_class, infer_source_group  # type: ignore

        s_class = infer_source_class(name, url)
        s_group = infer_source_group(name, url, s_class)
        return s_class, s_group
    except Exception:
        return None, None


def cadence_for_tier(tier: int) -> dict[str, int]:
    return {"interval_seconds": 600 if tier == 1 else 1800 if tier == 2 else 3600}


def endpoint_key_for_strategy(strategy: str) -> str:
    if strategy == "RSS":
        return "feed"
    if strategy in {"API", "SPA_API"}:
        return "api"
    return "latest"


def _default_api_contract() -> dict[str, Any]:
    return {
        "items_path": "items",
        "text_fields": ["text", "body", "content", "summary", "description"],
        "title_fields": ["title", "headline", "name"],
        "url_fields": ["url", "link", "href"],
        "published_at_fields": ["published_at", "publishedAt", "date", "updated_at"],
    }


def apply_profile_overrides(
    *,
    source_id: str,
    name: str,
    domain: str,
    url: str,
    policy: dict[str, Any],
) -> dict[str, Any]:
    md = dict(policy.get("metadata") or {})
    url_l = url.lower()
    name_l = name.lower()

    # Generic API hardening
    if policy.get("strategy") == "API":
        md.setdefault("api_contract", _default_api_contract())
        # Some public APIs reject GET on search endpoints; preserve future override hook.
        if "/graphql" in url_l:
            md.setdefault("api_request", {"method": "POST", "json": {"query": ""}})

    # Diário Oficial da União reading portal behaves like SPA and often needs render/XHR capture.
    if source_id == "dou_oficial" or ("in.gov.br" in domain and "leitura-digital" in url_l):
        policy["strategy"] = "SPA_HEADLESS"
        policy["pool"] = "HEAVY_RENDER_POOL"
        policy["endpoints"] = {"latest": url}
        capture = md.get("headless_capture") if isinstance(md.get("headless_capture"), dict) else {}
        capture.setdefault("url_contains", ["in.gov.br", "api", "json"])
        md["headless_capture"] = capture
        # DOU tends to be high-value but heavy; poll slightly less than RSS fast lanes.
        cadence = dict(policy.get("cadence") or {})
        cadence.setdefault("interval_seconds", 900)
        policy["cadence"] = cadence

    # TCU Acórdãos is a JSON endpoint (even if current path can drift).
    if source_id == "tcu_acordaos" or ("apps.tcu.gov.br" in domain and "/rest/" in url_l):
        policy["strategy"] = "API"
        policy["pool"] = "FAST_POOL"
        policy["endpoints"] = {"api": url}
        md.setdefault("api_contract", _default_api_contract())

    policy["metadata"] = md
    return policy


def convert_legacy_source_row(row: dict[str, Any]) -> dict[str, Any] | None:
    name = str(row.get("name") or "").strip()
    url = str(row.get("url") or "").strip()
    if not name or not url:
        return None

    parsed = urlparse(url)
    domain = (parsed.hostname or "unknown").lower()
    priority = str(row.get("priority") or "S2").strip().upper()
    tier = PRIORITY_MAP.get(priority, 3)
    strategy = infer_strategy(row.get("type"), url)
    pool = infer_pool(strategy)
    source_id = slugify_source_id(name)
    editoria = str(row.get("editoria") or "").strip() or None
    source_class, source_group = _safe_taxonomy(name, url)
    is_official = infer_is_official(domain, source_class)

    policy = {
        "source_id": source_id,
        "source_domain": domain,
        "tier": tier,
        "is_official": is_official,
        "lang": "pt-BR",
        "pool": pool,
        "strategy": strategy,
        "endpoints": {endpoint_key_for_strategy(strategy): url},
        "headers": {"User-Agent": INSTITUTIONAL_UA},
        "cadence": cadence_for_tier(tier),
        "limits": {
            "rate_limit_req_per_min": 10,
            "concurrency_per_domain": 1,
            "timeout_seconds": 30,
            "max_bytes": 5_000_000,
        },
        "observability": {
            "starvation_window_hours": 24,
            "yield_keys": ["anchors_count", "evidence_score"],
            "baseline_rolling": True,
            "calendar_profile": "business_hours_br",
        },
        "metadata": {
            "legacy_editoria": editoria,
            "legacy_name": name,
            "legacy_type": row.get("type"),
            "source_class": source_class,
            "source_group": source_group,
        },
    }
    policy = apply_profile_overrides(
        source_id=source_id,
        name=name,
        domain=domain,
        url=url,
        policy=policy,
    )

    return {
        "domain": domain,
        "name": name,
        "tier": tier,
        "is_official": is_official,
        "fetch_policy_json": policy,
    }


def load_legacy_sources(path: Path) -> list[dict[str, Any]]:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    rows = data.get("sources")
    if not isinstance(rows, list):
        return []
    return [r for r in rows if isinstance(r, dict)]


def convert_legacy_sources(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    converted: list[dict[str, Any]] = []
    seen_signatures: set[tuple[str, str]] = set()
    for row in rows:
        item = convert_legacy_source_row(row)
        if not item:
            continue
        policy = item.get("fetch_policy_json") or {}
        source_id = str((policy or {}).get("source_id") or "")
        endpoints = (policy or {}).get("endpoints") if isinstance((policy or {}).get("endpoints"), dict) else {}
        endpoint_url = str(next(iter((endpoints or {}).values()), "") or "")
        signature = (source_id, endpoint_url)
        if signature in seen_signatures:
            continue
        converted.append(item)
        seen_signatures.add(signature)
    return converted


def validate_converted_profiles(converted: list[dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    try:
        backend_dir = Path(__file__).resolve().parent
        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))
        from app.schemas.source_profile import SourceProfile  # type: ignore
    except Exception as exc:
        return [f"Validation unavailable (import error): {exc}"]

    for item in converted:
        try:
            SourceProfile(**item["fetch_policy_json"])
        except Exception as exc:
            errors.append(f"{item.get('name')} ({item.get('domain')}): {exc}")
    return errors


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_LEGACY_SOURCES_PATH)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--format", choices=["json", "yaml"], default="json")
    parser.add_argument("--validate", action="store_true", help="Validate converted fetch_policy_json with SourceProfile DSL")
    parser.add_argument("--pretty", action="store_true")
    return parser.parse_args()


def _dump_payload(payload: Any, fmt: str, pretty: bool) -> str:
    if fmt == "yaml":
        return yaml.safe_dump(payload, allow_unicode=True, sort_keys=False)
    if pretty:
        return json.dumps(payload, ensure_ascii=False, indent=2)
    return json.dumps(payload, ensure_ascii=False)


def main() -> int:
    args = _parse_args()
    if not args.input.exists():
        print(json.dumps({"status": "error", "reason": f"input not found: {args.input}"}), file=sys.stderr)
        return 2

    legacy_rows = load_legacy_sources(args.input)
    converted = convert_legacy_sources(legacy_rows)
    payload: dict[str, Any] = {
        "status": "ok",
        "input": str(args.input),
        "legacy_sources_total": len(legacy_rows),
        "converted_total": len(converted),
        "sources": converted,
    }
    if args.validate:
        errors = validate_converted_profiles(converted)
        payload["validation"] = {"ok": not errors, "errors": errors}
        if errors:
            payload["status"] = "fail"

    out = _dump_payload(payload, args.format, args.pretty)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(out + ("\n" if not out.endswith("\n") else ""), encoding="utf-8")
    else:
        print(out)
    return 0 if payload["status"] == "ok" else 3


if __name__ == "__main__":
    raise SystemExit(main())
