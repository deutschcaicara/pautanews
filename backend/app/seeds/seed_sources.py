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
        "domain": "agenciabrasil.ebc.com.br",
        "name": "Agência Brasil - Política",
        "tier": 1,
        "is_official": True,
        "fetch_policy_json": {
            "source_id": "agencia_brasil_politica",
            "source_domain": "agenciabrasil.ebc.com.br",
            "tier": 1,
            "pool": "FAST_POOL",
            "strategy": "RSS",
            "endpoints": {"feed": "https://agenciabrasil.ebc.com.br/rss/politica/feed.xml"},
            "cadence": {"interval_seconds": 300},
            "limits": {"rate_limit_req_per_min": 10},
        }
    },
    {
        "domain": "www12.senado.leg.br",
        "name": "Senado - Notícias",
        "tier": 1,
        "is_official": True,
        "fetch_policy_json": {
            "source_id": "senado_noticias",
            "source_domain": "senado.leg.br",
            "tier": 1,
            "pool": "FAST_POOL",
            "strategy": "RSS",
            "endpoints": {"feed": "https://www12.senado.leg.br/noticias/rss"},
            "cadence": {"interval_seconds": 600},
            "limits": {"rate_limit_req_per_min": 5},
        }
    },
    {
        "domain": "www.camara.leg.br",
        "name": "Câmara - Notícias",
        "tier": 1,
        "is_official": True,
        "fetch_policy_json": {
            "source_id": "camara_noticias",
            "source_domain": "camara.leg.br",
            "tier": 1,
            "pool": "FAST_POOL",
            "strategy": "HTML",
            "endpoints": {"latest": "https://www.camara.leg.br/noticias/"},
            "cadence": {"interval_seconds": 1800},
            "limits": {"rate_limit_req_per_min": 5},
        }
    },
    {
        "domain": "www.poder360.com.br",
        "name": "Poder360",
        "tier": 1,
        "is_official": False,
        "fetch_policy_json": {
            "source_id": "poder360",
            "source_domain": "poder360.com.br",
            "tier": 1,
            "pool": "FAST_POOL",
            "strategy": "RSS",
            "endpoints": {"feed": "https://www.poder360.com.br/feed/"},
            "cadence": {"interval_seconds": 300},
            "limits": {"rate_limit_req_per_min": 5},
        }
    },
    {
        "domain": "www.jota.info",
        "name": "JOTA - Notícias",
        "tier": 1,
        "is_official": False,
        "fetch_policy_json": {
            "source_id": "jota_noticias",
            "source_domain": "jota.info",
            "tier": 1,
            "pool": "FAST_POOL",
            "strategy": "RSS",
            "endpoints": {"feed": "https://www.jota.info/feed"},
            "cadence": {"interval_seconds": 600},
            "limits": {"rate_limit_req_per_min": 5},
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
        "name": "TCU - Notícias",
        "tier": 1,
        "is_official": True,
        "fetch_policy_json": {
            "source_id": "tcu_noticias",
            "source_domain": "tcu.gov.br",
            "tier": 1,
            "pool": "FAST_POOL",
            "strategy": "HTML",
            "endpoints": {"latest": "https://portal.tcu.gov.br/imprensa/noticias/"},
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
