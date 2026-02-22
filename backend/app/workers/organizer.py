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

logger = logging.getLogger(__name__)

@celery.task(name="app.workers.organize.run_organization")
def run_organization(profile_dict: Dict[str, Any], clean_text: str, content_hash: str):
    """Lighweight Event Builder (Plantão Path)."""
    profile = SourceProfile(**profile_dict)
    logger.info(f"Organizing event for {profile.source_id}")

    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_persist_data(profile, clean_text, content_hash))

async def _persist_data(profile: SourceProfile, text: str, content_hash: str):
    async with async_session_factory() as session:
        # 1. Upsert Document
        doc = Document(
            source_id=profile.id,
            title=f"Sugestão de Pauta: {profile.source_domain}",
            url=profile.endpoints.get("feed") or profile.endpoints.get("latest") or profile.endpoints.get("api"),
            raw_content=text[:2000],
            content_hash=content_hash
        )
        session.add(doc)

        # 2. Simple Event creation
        event = Event(
            status=EventStatus.NEW,
            summary=f"Novo sinal de pauta em {profile.source_domain}",
            score_plantao=50.0
        )
        session.add(event)
        await session.commit()
        logger.info(f"Persisted doc and event for {profile.source_id}")
