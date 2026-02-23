"""Sync seed data for journalistic sources from legacy ~/news (Blueprint §6).

Goals:
- import all curated legacy sources
- preserve multiple endpoints from the same domain
- avoid exact duplicate crawlers (same source_id + endpoint)
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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LEGACY_YAML_PATH = Path("/home/diego/news/bootstrap/config/sources.yaml")
INTERNAL_YAML_PATH = Path("/app/sources_legacy.yaml")


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


@dataclass
class SyncStats:
    inserted: int = 0
    updated: int = 0
    duplicates_disabled: int = 0
    skipped_invalid: int = 0
    legacy_total: int = 0
    converted_total: int = 0

    def as_dict(self) -> dict[str, int]:
        return {
            "inserted": self.inserted,
            "updated": self.updated,
            "duplicates_disabled": self.duplicates_disabled,
            "skipped_invalid": self.skipped_invalid,
            "legacy_total": self.legacy_total,
            "converted_total": self.converted_total,
        }


async def sync_sources(*, disable_exact_duplicates: bool = True) -> SyncStats:
    conv = _load_convert_module()
    path = _choose_legacy_path()

    legacy_rows = conv.load_legacy_sources(path)
    converted = conv.convert_legacy_sources(legacy_rows)
    stats = SyncStats(legacy_total=len(legacy_rows), converted_total=len(converted))

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
                # Keep existing enabled flag if user disabled manually.
                src.fetch_policy_json = policy
                stats.updated += 1
                continue

            src = Source(
                domain=str(item["domain"]),
                name=str(item["name"]),
                tier=int(item["tier"]),
                is_official=bool(item["is_official"]),
                fetch_policy_json=policy,
                enabled=True,
            )
            session.add(src)
            existing_rows.append(src)
            by_signature.setdefault(sig, []).append(src)
            stats.inserted += 1

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

