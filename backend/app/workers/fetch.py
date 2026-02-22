"""Unified fetcher worker — handles RSS, HTML, and API strategies.

Implements Blueprint §9.1 and §13.
"""
from __future__ import annotations

import logging
import hashlib
import httpx
from datetime import datetime
from typing import Any, Dict, Optional

from app.celery_app import celery
from app.db import async_session_factory
from app.models.fetch_attempt import FetchAttempt
from app.models.snapshot import Snapshot
from app.schemas.source_profile import SourceProfile, StrategyType

logger = logging.getLogger(__name__)

import asyncio

@celery.task(name="app.workers.fetch.run_fetch", bind=True, max_retries=3)
def run_fetch(self, profile_dict: Dict[str, Any]):
    """Entry point for all fetch jobs. Runs as a sync Celery task."""
    profile = SourceProfile(**profile_dict)
    logger.info(f"Starting fetch for {profile.source_id}")

    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(_async_run_fetch(profile))
    except Exception as exc:
        logger.error(f"Fetch failed for {profile.source_id}: {exc}")
        self.retry(exc=exc, countdown=60)

async def _async_run_fetch(profile: SourceProfile):
    """Async implementation of the robust fetcher."""
    url = profile.endpoints.get("feed") or profile.endpoints.get("latest") or profile.endpoints.get("api")
    if not url:
        logger.warning(f"No URL found for {profile.source_id}")
        return

    async with httpx.AsyncClient(
        headers=profile.headers,
        timeout=profile.limits.timeout_seconds,
        follow_redirects=True,
    ) as client:
        # 1. Fetch with ETag/IMS strategy (Simple for MVP)
        try:
            resp = await client.get(url)
            resp.raise_for_status()
        except Exception as e:
            logger.error(f"HTTP GET failed: {e}")
            # Record failed attempt (M12 DATA_STARVATION)
            return

        body = resp.text
        content_hash = hashlib.sha256(body.encode()).hexdigest()
        
        # 2. Snapshot & Persistence
        async with async_session_factory() as session:
            # Here we would check content_hash against snapshots to avoid re-processing
            # and create Snapshot + FetchAttempt records
            
            # Simple placeholder for M1 models interaction
            attempt = FetchAttempt(
                source_id=profile.id,
                url=url,
                status_code=resp.status_code,
                latency_ms=int(resp.elapsed.total_seconds() * 1000),
                bytes=len(body),
                pool=profile.pool,
                snapshot_hash=content_hash
            )
            session.add(attempt)
            await session.commit()
            
        # 3. Trigger Extraction (M3.2)
        celery.send_task(
            "app.workers.extract.run_extraction",
            args=[profile.model_dump(), body, content_hash],
            queue="extract_fast" 
        )
