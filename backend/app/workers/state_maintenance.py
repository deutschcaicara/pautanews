"""Periodic state maintenance tasks (timeouts / TTL)."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.celery_app import celery
from app.config import settings
from app.db import async_session_factory
from app.event_state_service import ensure_event_has_initial_state, transition_event_status
from app.models.event import Event, EventStatus
from app.state_engine import evaluate_state_transition

logger = logging.getLogger(__name__)


@celery.task(name="app.workers.state_maintenance.run_state_maintenance")
def run_state_maintenance() -> None:
    asyncio.run(_run_state_maintenance())


async def _run_state_maintenance() -> None:
    now = datetime.now(timezone.utc)
    transitioned = 0
    async with async_session_factory() as session:
        events = (
            await session.execute(
                select(Event).where(
                    Event.status.in_(
                        [
                            EventStatus.HYDRATING.value,
                            EventStatus.QUARANTINE.value,
                        ]
                    )
                )
            )
        ).scalars().all()

        for event in events:
            await ensure_event_has_initial_state(session, event=event)
            if str(event.status) == EventStatus.HYDRATING.value:
                next_status = evaluate_state_transition(
                    event,
                    current_pool="FAST_POOL",
                    hydration_start_at=event.first_seen_at,
                )
                if next_status == EventStatus.PARTIAL_ENRICH:
                    changed = await transition_event_status(
                        session,
                        event=event,
                        new_status=EventStatus.PARTIAL_ENRICH,
                        status_reason="HYDRATION_TIMEOUT_FAST",
                    )
                    transitioned += int(changed)
                    if changed:
                        celery.send_task(
                            "app.workers.alerts.run_alerts",
                            args=[event.id, {"score": float(event.score_plantao or 0.0), "reasons": ["HYDRATION_TIMEOUT_FAST"]}, {}],
                            queue="alerts",
                        )
            elif str(event.status) == EventStatus.QUARANTINE.value:
                cutoff = now - timedelta(seconds=settings.QUARANTINE_TTL_S)
                if (event.updated_at or event.first_seen_at) <= cutoff:
                    changed = await transition_event_status(
                        session,
                        event=event,
                        new_status=EventStatus.EXPIRED,
                        status_reason="QUARANTINE_TTL_EXPIRED",
                    )
                    transitioned += int(changed)
                    if changed:
                        celery.send_task(
                            "app.workers.alerts.run_alerts",
                            args=[event.id, {"score": float(event.score_plantao or 0.0), "reasons": ["QUARANTINE_TTL_EXPIRED"]}, {}],
                            queue="alerts",
                        )

        await session.commit()

    if transitioned:
        logger.info("State maintenance transitioned %s events", transitioned)
