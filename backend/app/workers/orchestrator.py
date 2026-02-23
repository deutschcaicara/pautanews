"""Orchestration worker — Blueprint §5.2.

This worker runs on a schedule (Beat) and fans out fetch tasks for all 
enabled sources based on their individual cadence.
"""
from __future__ import annotations

import logging
import asyncio

from app.celery_app import celery
from app.scheduler import get_active_source_profiles
from app.schemas.source_profile import PoolType

logger = logging.getLogger(__name__)

@celery.task(name="app.workers.orchestrate_fetches")
def orchestrate_fetches():
    """Celery Beat task to fan out fetches."""
    profiles = asyncio.run(get_active_source_profiles(only_due=True))

    for profile in profiles:
        # Determine routing key based on pool
        routing_key = "fetch_fast"
        if profile.pool == PoolType.HEAVY_RENDER_POOL:
            routing_key = "fetch_render"
        elif profile.pool == PoolType.DEEP_EXTRACT_POOL:
            routing_key = "fetch_deep"

        logger.info(f"Scheduling fetch for {profile.source_id} to queue {routing_key}")
        
        # Dispatch the fetch task (implemented in M3/M5/M6)
        celery.send_task(
            "app.workers.fetch.run_fetch",
            args=[profile.model_dump()],
            queue=routing_key,
            routing_key=routing_key
        )
