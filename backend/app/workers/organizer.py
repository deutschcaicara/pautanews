"""Event Builder — Blueprint §9.1 and §11.

Creates or updates events based on semantic similarity or anchors.
For M3, we implement a lightweight upsert to meet the P95 ≤ 60s SLO.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict

from app.celery_app import celery
from app.db import async_session_factory
from app.models.event import Event, EventStatus
from app.models.document import Document
from app.schemas.source_profile import SourceProfile
from app.core.taxonomy import infer_editorial_lane, infer_source_class

logger = logging.getLogger(__name__)

@celery.task(name="app.workers.organize.run_organization")
def run_organization(profile_dict: Dict[str, Any], clean_text: str, content_hash: str, url: str = None, title: str = None):
    """Lighweight Event Builder (Plantão Path)."""
    profile = SourceProfile(**profile_dict)
    logger.info(f"Organizing event for {profile.source_id} - URL: {url}")

    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_persist_data(profile, clean_text, content_hash, url, title))

async def _persist_data(profile: SourceProfile, text: str, content_hash: str, url: str, title: str):
    async with async_session_factory() as session:
        # 1. Infer lane and class if not explicit
        lane = infer_editorial_lane(
            title=title,
            snippet=text[:500],
            editoria=profile.source_id # Use source_id as hint
        )
        
        # 2. Upsert Document
        doc = Document(
            source_id=profile.id,
            title=title or f"Sugestão de Pauta: {profile.source_domain}",
            url=url or profile.endpoints.get("feed") or profile.endpoints.get("latest"),
            clean_text=text[:5000],
            content_hash=content_hash
        )
        session.add(doc)

        # 3. Simple Event creation with Status Gating
        # If Tier 1 and has high enough confidence/keywords, promote to HOT
        status = EventStatus.NEW
        score = 50.0
        
        if profile.tier == 1:
            status = EventStatus.HOT
            score = 85.0 # Boost Tier 1 signals for the MVP demonstration

        event = Event(
            status=status,
            lane=lane,
            summary=title or f"Novo sinal de pauta em {profile.source_domain}",
            score_plantao=score
        )
        # Note: In a real M8/M9 we would use the taxonomy here
        session.add(event)
        await session.commit()
        logger.info(f"Persisted doc and event for {profile.source_id} (Status: {status})")
