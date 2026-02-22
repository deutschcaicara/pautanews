"""Scoring Worker — Blueprint §12.

Aggregates multiple metrics to compute dual event scores.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict

from sqlalchemy import select, func
from app.celery_app import celery
from app.db import async_session_factory
from app.models.event import Event, EventDoc
from app.models.document import Document
from app.models.anchor import DocEvidenceFeature
from app.models.source import Source
from app.models.score import EventScore
from app.scoring.plantao import calculate_plantao_score
from app.scoring.oceano import calculate_oceano_score

logger = logging.getLogger(__name__)

@celery.task(name="app.workers.score.run_scoring")
def run_scoring(event_id: int):
    """Fetch event stats and compute both scores."""
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_compute_scores(event_id))

async def _compute_scores(event_id: int):
    async with async_session_factory() as session:
        # 1. Fetch Event and first_seen_at
        stmt = select(Event).where(Event.id == event_id)
        result = await session.execute(stmt)
        event = result.scalar()
        if not event:
            return

        # 2. Fetch Source metrics (diversity & highest tier)
        stmt = (
            select(Source.tier, Source.is_official)
            .join(EventDoc, EventDoc.source_id == Source.id)
            .where(EventDoc.event_id == event_id)
        )
        result = await session.execute(stmt)
        sources_info = result.all()
        
        source_count = len(sources_info)
        highest_tier = min([s.tier for s in sources_info]) if sources_info else 3
        has_official = any([s.is_official for s in sources_info])
        has_tier1 = any([s.tier == 1 for s in sources_info])

        # 3. Fetch Velocity (docs in last 30 mins)
        tz = event.first_seen_at.tzinfo
        thirty_mins_ago = datetime.now(tz) - timedelta(minutes=30)
        stmt = select(func.count(EventDoc.doc_id)).where(
            EventDoc.event_id == event_id, 
            EventDoc.seen_at >= thirty_mins_ago
        )
        result = await session.execute(stmt)
        velocity = result.scalar() or 0

        # 4. Fetch Evidence Metrics
        stmt = (
            select(func.max(DocEvidenceFeature.evidence_score))
            .join(EventDoc, EventDoc.doc_id == DocEvidenceFeature.doc_id)
            .where(EventDoc.event_id == event_id)
        )
        result = await session.execute(stmt)
        max_evidence = result.scalar() or 0.0

        # 5. Compute Scores
        p_data = calculate_plantao_score(
            tier=highest_tier,
            velocity=float(velocity),
            source_count=source_count,
            first_seen_at=event.first_seen_at
        )
        oa_data = calculate_oceano_score(
            evidence_score=max_evidence,
            has_tier1_coverage=has_tier1, 
            is_official=has_official
        )

        # 6. Persistence
        stmt = select(EventScore).where(EventScore.event_id == event_id)
        result = await session.execute(stmt)
        score_obj = result.scalar()
        
        if not score_obj:
            score_obj = EventScore(event_id=event_id)
            session.add(score_obj)
            
        score_obj.score_plantao = p_data["score"]
        score_obj.score_oceano_azul = oa_data["score"]
        score_obj.reasons_json = {
            "plantao": p_data["reasons"],
            "oceano": oa_data["reasons"]
        }
        
        # Also update the primary event record for easier dashboard querying
        event.score_plantao = p_data["score"]
        
        await session.commit()
        logger.info(f"Scores updated for event {event_id}: P={score_obj.score_plantao} OA={score_obj.score_oceano_azul}")

    # Trigger Alerts if needed (M13)
    if p_data['score'] > 70.0 or oa_data['score'] > 70.0:
        celery.send_task(
            "app.workers.alerts.run_alerts",
            args=[event_id, p_data, oa_data],
            queue="alerts"
        )
