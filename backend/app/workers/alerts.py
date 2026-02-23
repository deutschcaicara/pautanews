"""Alerts worker — minimal state-aware alert persistence.

Sprint 0 goal: prevent runtime failures from missing task.
This implementation already uses EventAlertState cooldown to reduce spam.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select

from app.celery_app import celery
from app.config import settings
from app.db import async_session_factory
from app.models.alert import Alert, EventAlertState
from app.models.event import Event

logger = logging.getLogger(__name__)


def _alert_hash(event_id: int, p_data: dict[str, Any] | None, oa_data: dict[str, Any] | None) -> str:
    payload = {
        "event_id": event_id,
        "plantao_reasons": (p_data or {}).get("reasons", []),
        "oceano_reasons": (oa_data or {}).get("reasons", []),
        "plantao_band": int(float((p_data or {}).get("score", 0)) // 5),
        "oceano_band": int(float((oa_data or {}).get("score", 0)) // 5),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=True).encode("utf-8")).hexdigest()


@celery.task(name="app.workers.alerts.run_alerts")
def run_alerts(event_id: int, p_data: dict[str, Any] | None = None, oa_data: dict[str, Any] | None = None) -> None:
    """Persist alert with simple cooldown/hash dedupe."""
    asyncio.run(_async_run_alerts(event_id, p_data or {}, oa_data or {}))


async def _async_run_alerts(event_id: int, p_data: dict[str, Any], oa_data: dict[str, Any]) -> None:
    now = datetime.now(timezone.utc)
    payload = {
        "event_id": event_id,
        "plantao": p_data,
        "oceano": oa_data,
        "generated_at": now.isoformat(),
    }
    hash_value = _alert_hash(event_id, p_data, oa_data)

    async with async_session_factory() as session:
        event = (await session.execute(select(Event).where(Event.id == event_id))).scalar()
        if not event:
            logger.warning("Alert skipped: event %s not found", event_id)
            return

        state = (await session.execute(select(EventAlertState).where(EventAlertState.event_id == event_id))).scalar()
        if not state:
            state = EventAlertState(event_id=event_id)
            session.add(state)
            await session.flush()

        if state.cooldown_until and state.cooldown_until > now:
            logger.info("Alert cooldown active for event %s until %s", event_id, state.cooldown_until.isoformat())
            return
        if state.last_alert_hash and state.last_alert_hash == hash_value:
            logger.info("Alert dedup hash matched for event %s; skipping", event_id)
            return

        alert = Alert(
            event_id=event_id,
            channel="internal",
            payload_json=payload,
            status="SENT",
        )
        session.add(alert)

        state.last_alert_hash = hash_value
        state.last_alert_at = now
        state.cooldown_until = now + timedelta(seconds=settings.ALERT_COOLDOWN_S)

        await session.commit()
        logger.info("Alert persisted for event %s", event_id)

