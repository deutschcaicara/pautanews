"""Initial seed data for journalistic sources — Blueprint §6."""
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from app.db import async_session_factory
from app.models.source import Source

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

INITIAL_SOURCES = [
    {
        "domain": "g1.globo.com",
        "name": "G1 - Política",
        "tier": 1,
        "is_official": False,
        "fetch_policy_json": {
            "source_id": "g1_politica",
            "source_domain": "g1.globo.com",
            "tier": 1,
            "pool": "FAST_POOL",
            "strategy": "RSS",
            "endpoints": {"feed": "https://g1.globo.com/rss/g1/politica/"},
            "cadence": {"interval_seconds": 60},
            "limits": {"rate_limit_req_per_min": 10},
        }
    },
    {
        "domain": "in.gov.br",
        "name": "Diário Oficial da União",
        "tier": 1,
        "is_official": True,
        "fetch_policy_json": {
            "source_id": "dou_oficial",
            "source_domain": "in.gov.br",
            "tier": 1,
            "pool": "DEEP_EXTRACT_POOL",
            "strategy": "HTML",
            "endpoints": {"latest": "https://www.in.gov.br/leitura-digital"},
            "cadence": {"cron": "0 * * * *"}, # Hourly
            "limits": {"rate_limit_req_per_min": 5},
        }
    },
    {
        "domain": "tcu.gov.br",
        "name": "TCU - Acórdãos",
        "tier": 1,
        "is_official": True,
        "fetch_policy_json": {
            "source_id": "tcu_acordaos",
            "source_domain": "tcu.gov.br",
            "tier": 1,
            "pool": "DEEP_EXTRACT_POOL",
            "strategy": "API",
            "endpoints": {"api": "https://pesquisa.apps.tcu.gov.br/rest/publico/base/acordao/pesquisa"},
            "cadence": {"interval_seconds": 3600},
            "limits": {"rate_limit_req_per_min": 2},
        }
    }
]

async def seed_sources():
    async with async_session_factory() as session:
        for src_data in INITIAL_SOURCES:
            logger.info(f"Seeding source: {src_data['domain']}")
            source = Source(**src_data)
            session.add(source)
        try:
            await session.commit()
            logger.info("Seeding completed successfully.")
        except Exception as e:
            await session.rollback()
            logger.error(f"Error seeding sources: {e}")

if __name__ == "__main__":
    asyncio.run(seed_sources())
