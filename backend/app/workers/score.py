"""Scoring Worker — Blueprint §12.

Aggregates multiple metrics to compute dual event scores.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta

from sqlalchemy import select, func

from app.celery_app import celery
from app.db import async_session_factory
from app.event_state_service import ensure_event_has_initial_state, transition_event_status
from app.metrics import EVENT_SCORES_OBS, UNVERIFIED_VIRAL_EVENTS_TOTAL
from app.models.anchor import DocEvidenceFeature
from app.models.event import Event, EventDoc, EventStatus
from app.models.source import Source
from app.models.score import EventScore
from app.scoring.plantao import calculate_plantao_score
from app.scoring.oceano import calculate_oceano_score
from app.state_engine import check_quarantine, check_unverified_viral

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.score.run_scoring")
def run_scoring(event_id: int):
    """Fetch event stats and compute both scores."""
    asyncio.run(_compute_scores(event_id))


async def _compute_scores(event_id: int):
    p_data: dict | None = None
    oa_data: dict | None = None
    state_changed = False
    new_state_name: str | None = None

    async with async_session_factory() as session:
        # 1. Fetch Event and first_seen_at
        stmt = select(Event).where(Event.id == event_id)
        result = await session.execute(stmt)
        event = result.scalar()
        if not event:
            return
        await ensure_event_has_initial_state(session, event=event)

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
            select(
                func.max(DocEvidenceFeature.evidence_score),
                func.bool_or(DocEvidenceFeature.has_pdf),
            )
            .join(EventDoc, EventDoc.doc_id == DocEvidenceFeature.doc_id)
            .where(EventDoc.event_id == event_id)
        )
        result = await session.execute(stmt)
        evidence_row = result.one_or_none()
        max_evidence = (evidence_row[0] if evidence_row else 0.0) or 0.0
        has_pdf_evidence = bool((evidence_row[1] if evidence_row else False) or False)

        # 4b. Coverage lag proxy (minutes) based on Tier-1 presence
        coverage_lag_minutes = None if has_tier1 else max(
            0.0,
            (datetime.now(tz) - event.first_seen_at).total_seconds() / 60.0,
        )

        # 4c. Heuristics for impact/trust penalties
        impact_signal = 0.0
        if has_official:
            impact_signal += 2.0
        if max_evidence >= 3.0:
            impact_signal += 2.5
        if velocity >= 3:
            impact_signal += 1.5
        impact_signal += min(4.0, source_count * 0.5)

        trust_penalty = 0.0
        if not has_official and source_count < 2:
            trust_penalty += 4.0
        if not has_tier1 and max_evidence < 1.0:
            trust_penalty += 3.0

        # 5. Compute Scores
        p_data = calculate_plantao_score(
            tier=highest_tier,
            velocity=float(velocity),
            source_count=source_count,
            first_seen_at=event.first_seen_at,
            impact_signal=impact_signal,
            trust_penalty=trust_penalty,
        )
        oa_data = calculate_oceano_score(
            evidence_score=max_evidence,
            has_tier1_coverage=has_tier1, 
            is_official=has_official,
            coverage_lag_minutes=coverage_lag_minutes,
            has_pdf_evidence=has_pdf_evidence,
            trust_penalty=trust_penalty,
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
        event.last_seen_at = datetime.now(event.first_seen_at.tzinfo or None)

        # 7. Flags / state heuristics (Blueprint §13 minimal integration)
        flags = dict(event.flags_json or {})
        if check_unverified_viral(float(velocity), source_count):
            flags["UNVERIFIED_VIRAL"] = True
            UNVERIFIED_VIRAL_EVENTS_TOTAL.labels(lane=(event.lane or "geral")).inc()
        else:
            flags.pop("UNVERIFIED_VIRAL", None)
        event.flags_json = flags or None

        candidate_state = None
        if check_quarantine(float(p_data["score"]), source_count):
            candidate_state = EventStatus.QUARANTINE
        elif float(p_data["score"]) >= 70.0:
            candidate_state = EventStatus.HOT
        elif event.status in {EventStatus.NEW, EventStatus.HYDRATING} and float(p_data["score"]) < 70.0:
            candidate_state = EventStatus.HYDRATING

        if candidate_state:
            state_changed = await transition_event_status(
                session,
                event=event,
                new_status=candidate_state,
                status_reason=(
                    "SCORE_QUARANTINE_HEURISTIC"
                    if candidate_state == EventStatus.QUARANTINE
                    else "SCORE_THRESHOLD_HOT"
                    if candidate_state == EventStatus.HOT
                    else "SCORE_RECOMPUTE"
                ),
            )
            if state_changed:
                new_state_name = candidate_state.value

        await session.commit()
        EVENT_SCORES_OBS.labels(score_type="SCORE_PLANTAO", lane=(event.lane or "geral")).observe(float(p_data["score"]))
        EVENT_SCORES_OBS.labels(score_type="SCORE_OCEANO_AZUL", lane=(event.lane or "geral")).observe(float(oa_data["score"]))
        logger.info(f"Scores updated for event {event_id}: P={score_obj.score_plantao} OA={score_obj.score_oceano_azul}")

    # Trigger alerts only on state transition (§13.5 anti-spam)
    if state_changed and p_data and oa_data:
        celery.send_task(
            "app.workers.alerts.run_alerts",
            args=[event_id, p_data, oa_data],
            queue="alerts"
        )

    # Trigger Smart Drafting (M19)
    if p_data and oa_data and (p_data['score'] > 50.0 or oa_data['score'] > 50.0):
        celery.send_task(
            "app.workers.draft.run_drafting",
            args=[event_id],
            queue="nlp"
        )
