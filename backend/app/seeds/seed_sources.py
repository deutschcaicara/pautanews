"""Initial seed data for journalistic sources — Blueprint §6.
Loads directly from legacy YAML for maximum fidelity.
"""
import asyncio
import logging
import yaml
from pathlib import Path
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db import async_session_factory
from app.models.source import Source
from app.core.taxonomy import infer_source_class, infer_source_group

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

LEGACY_YAML_PATH = Path("/home/diego/news/bootstrap/config/sources.yaml")
INTERNAL_YAML_PATH = Path("/app/sources_legacy.yaml")
INSTITUTIONAL_UA = "RadarHardNews/1.0 (Institutional; newsroom monitoring)"

async def seed_sources():
    path = LEGACY_YAML_PATH if LEGACY_YAML_PATH.exists() else INTERNAL_YAML_PATH
    if not path.exists():
        logger.error(f"Legacy sources YAML not found at {LEGACY_YAML_PATH} nor {INTERNAL_YAML_PATH}")
        return

    with open(path, "r") as f:
        data = yaml.safe_load(f)
    
    legacy_sources = data.get("sources", [])
    logger.info(f"Found {len(legacy_sources)} sources in legacy YAML.")

    priority_map = {"S0": 1, "S1": 2, "S2": 3}
    type_map = {"rss": "RSS", "watch": "HTML"}

    async with async_session_factory() as session:
        # Check existing sources to avoid duplicate endpoint rows while preserving
        # multiple useful endpoints per same domain (agenda/noticias/comunicados).
        stmt = select(Source)
        result = await session.execute(stmt)
        existing_sources = result.scalars().all()
        existing_source_ids: set[str] = set()
        existing_endpoint_urls: set[str] = set()
        for src in existing_sources:
            try:
                policy = dict(src.fetch_policy_json or {})
            except Exception:
                policy = {}
            sid = str(policy.get("source_id") or "").strip()
            if sid:
                existing_source_ids.add(sid)
            endpoints = policy.get("endpoints") if isinstance(policy.get("endpoints"), dict) else {}
            for endpoint_url in (endpoints or {}).values():
                if endpoint_url:
                    existing_endpoint_urls.add(str(endpoint_url).strip())

        new_sources_count = 0
        for s in legacy_sources:
            name = s.get("name")
            url = s.get("url")
            stype = s.get("type")
            editoria = s.get("editoria")
            priority = s.get("priority", "S2")
            
            domain = urlparse(url).hostname or "unknown" if url else "unknown"
            tier = priority_map.get(priority, 3)
            strategy = type_map.get(stype, "HTML")
            source_id = name.lower().replace(" ", "_").replace("-", "_").replace(".", "_")
            endpoint_key = "feed" if strategy == "RSS" else "latest"
            endpoint_url = str(url).strip()
            if source_id in existing_source_ids or endpoint_url in existing_endpoint_urls:
                continue
            
            # Use taxonomy to infer class and group
            s_class = infer_source_class(name, url)
            s_group = infer_source_group(name, url, s_class)

            policy = {
                "source_id": source_id,
                "source_domain": domain,
                "tier": tier,
                "is_official": bool(".gov.br" in domain or ".leg.br" in domain or ".jus.br" in domain or s_class == "primary"),
                "lang": "pt-BR",
                "pool": "FAST_POOL",
                "strategy": strategy,
                "endpoints": {endpoint_key: endpoint_url},
                "headers": {"User-Agent": INSTITUTIONAL_UA},
                "cadence": {"interval_seconds": 600 if tier == 1 else 1800 if tier == 2 else 3600},
                "limits": {"rate_limit_req_per_min": 10},
                "observability": {
                    "starvation_window_hours": 24,
                    "yield_keys": ["anchors_count", "evidence_score"],
                    "baseline_rolling": True,
                    "calendar_profile": "business_hours_br",
                },
                "metadata": {
                    "legacy_editoria": editoria,
                    "source_class": s_class,
                    "source_group": s_group
                }
            }
            
            source = Source(
                domain=domain,
                name=name,
                tier=tier,
                is_official=bool(policy["is_official"]),
                fetch_policy_json=policy
            )
            session.add(source)
            existing_source_ids.add(source_id)
            existing_endpoint_urls.add(endpoint_url)
            new_sources_count += 1

        if new_sources_count > 0:
            try:
                await session.commit()
                logger.info(f"Seeded {new_sources_count} new sources successfully.")
            except Exception as e:
                await session.rollback()
                logger.error(f"Error seeding sources: {e}")
        else:
            logger.info("No new sources to seed.")

if __name__ == "__main__":
    asyncio.run(seed_sources())
