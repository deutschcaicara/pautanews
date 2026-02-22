"""Dynamic Scheduler for Radar Hard News.

This module provides the logic to map database-stored Source profiles
to Celery periodic tasks without requiring hardcoded beat schedules.
"""
from __future__ import annotations

import logging
from sqlalchemy import select
from app.db import async_session_factory
from app.models.source import Source
from app.schemas.source_profile import SourceProfile

logger = logging.getLogger(__name__)

async def get_active_source_profiles() -> list[SourceProfile]:
    """Fetch enabled sources and validate their profiles."""
    profiles = []
    async with async_session_factory() as session:
        result = await session.execute(
            select(Source).where(Source.enabled == True)
        )
        sources = result.scalars().all()

        for source in sources:
            try:
                profile = SourceProfile(**source.fetch_policy_json)
                profiles.append(profile)
            except Exception as e:
                logger.error(f"Invalid profile for source {source.id} ({source.domain}): {e}")
    
    return profiles

def schedule_fetches(celery_app):
    """
    In a real-world scenario with django-celery-beat or equivalent, 
    we would update the PeriodicTask table here.
    For this MVP, we will use a dedicated beat task that orchestrates 
    the fan-out of fetch jobs based on current DB state.
    """
    # This will be called by the orchestrator task defined in app/workers/orchestrator.py
    pass
