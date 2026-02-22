"""Scoring Worker — Blueprint §12.

Aggregates multiple metrics to compute dual event scores.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.celery_app import celery
from app.db import async_session_factory
from app.models.score import EventScore
from app.scoring.plantao import calculate_plantao_score
from app.scoring.oceano import calculate_oceano_score

logger = logging.getLogger(__name__)

@celery.task(name="app.workers.score.run_scoring")
def run_scoring(event_id: int):
    """Fetch event stats and compute both scores."""
    # Since this is a worker, we'd normally query the DB for:
    # - velocity (docs in last X min)
    # - source count
    # - evidence_score (from anchors)
    # - Tier-1 coverage presence
    
    # Placeholder logic for MVP
    logger.info(f"Computing scores for event {event_id}")

    # Mock data for demonstration
    p_data = calculate_plantao_score(tier=1, velocity=10.0, source_count=2, first_seen_at=None) # Correct first_seen_at would be passed
    oa_data = calculate_oceano_score(evidence_score=5.0, has_tier1_coverage=False, is_official=True)

    # Persistence to M1 model
    # Note: In production, this would be an async DB call
    logger.info(f"Scores for {event_id}: Plantão={p_data['score']}, Oceano Azul={oa_data['score']}")
    
    # Trigger Alerts if needed (M13)
    if p_data['score'] > 50.0 or oa_data['score'] > 50.0:
        celery.send_task(
            "app.workers.alerts.run_alerts",
            args=[event_id, p_data, oa_data],
            queue="alerts"
        )
