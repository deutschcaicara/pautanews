"""Feedback API — Blueprint §8 / §13.1 / §18.

Captures editorial actions (merge, ignore, snooze) for backtesting.
"""
from __future__ import annotations

import logging
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.celery_app import celery
from app.db import get_session
from app.event_state_service import transition_event_status
from app.merge_service import merge_event_into
from app.models.feedback import FeedbackEvent
from app.models.event import Event, EventStatus
from app.split_service import split_event_by_docs
from app.state_engine import action_gating_decision

router = APIRouter(prefix="/feedback", tags=["editorial"])
logger = logging.getLogger(__name__)


class FeedbackActionPayload(BaseModel):
    user_id: str | None = None
    target_event_id: int | None = None
    to_event_id: int | None = None
    doc_ids: list[int] = Field(default_factory=list)
    new_summary: str | None = None
    new_lane: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class FeedbackActionResponse(BaseModel):
    status: str
    event_id: int
    action: str
    state_changed: bool
    merge: dict[str, Any] | None = None


@router.post("/{event_id}/action")
async def record_feedback(
    event_id: int,
    action: str,
    payload: FeedbackActionPayload,
    db: AsyncSession = Depends(get_session)
) -> FeedbackActionResponse:
    """§18: Toda ação editorial gera feedback_event."""
    payload_data = payload.model_dump(exclude_none=True)
    
    # Valid actions (§18)
    if action not in ["IGNORE", "SNOOZE", "PAUTAR", "MERGE", "SPLIT"]:
        raise HTTPException(status_code=400, detail="Invalid editorial action")

    # 1. Persist feedback event
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")

    allowed, blocked_reason = action_gating_decision(event, action=action)
    if not allowed:
        raise HTTPException(status_code=409, detail=blocked_reason or "Action blocked by state gating")

    feedback = FeedbackEvent(
        event_id=event_id,
        action=action,
        payload_json=payload_data,
        actor=payload_data.get("user_id", "anonymous")
    )
    db.add(feedback)
    
    # 2. Update event state based on action (§13)
    # (Simple mapping for MVP)
    state_changed = False
    merge_payload: Dict[str, Any] | None = None
    rescore_event_ids: set[int] = set()
    if action == "IGNORE":
        state_changed = await transition_event_status(
            db,
            event=event,
            new_status=EventStatus.IGNORED,
            status_reason="FEEDBACK_IGNORE",
        )
    elif action == "SNOOZE":
        state_changed = await transition_event_status(
            db,
            event=event,
            new_status=EventStatus.QUARANTINE,
            status_reason="FEEDBACK_SNOOZE",
        )
    elif action == "PAUTAR":
        state_changed = await transition_event_status(
            db,
            event=event,
            new_status=EventStatus.HOT,
            status_reason="FEEDBACK_PAUTAR",
        )
    elif action == "MERGE":
        target_event_id = payload_data.get("target_event_id") or payload_data.get("to_event_id")
        try:
            target_event_id = int(target_event_id)
        except Exception:
            raise HTTPException(status_code=400, detail="MERGE requires payload.target_event_id")
        if target_event_id == event_id:
            raise HTTPException(status_code=400, detail="Cannot merge event into itself")

        target_event = (await db.execute(select(Event).where(Event.id == target_event_id))).scalar()
        if not target_event:
            raise HTTPException(status_code=404, detail="Target event not found")
        if target_event.canonical_event_id:
            raise HTTPException(status_code=409, detail=f"Target event merged into {target_event.canonical_event_id}")

        target_allowed, target_blocked = action_gating_decision(target_event, action="MERGE")
        if not target_allowed:
            raise HTTPException(status_code=409, detail=f"Target blocked: {target_blocked}")

        merge_result = await merge_event_into(
            db,
            absorbed_event=event,
            canonical_event=target_event,
            reason_code="EDITORIAL_MERGE",
            status_reason="EDITORIAL_MERGE",
            evidence_json={
                "actor": payload_data.get("user_id", "anonymous"),
                "source": "feedback_api",
            },
        )
        state_changed = bool(merge_result.merged)
        merge_payload = {
            "from_event_id": merge_result.from_event_id,
            "to_event_id": merge_result.to_event_id,
            "moved_docs": merge_result.moved_docs,
            "deduped_docs": merge_result.deduped_docs,
        }
        if merge_result.merged:
            rescore_event_ids.add(int(merge_result.to_event_id))
    elif action == "SPLIT":
        split_doc_ids = payload_data.get("doc_ids") or (payload_data.get("metadata") or {}).get("doc_ids") or []
        try:
            split_result = await split_event_by_docs(
                db,
                source_event=event,
                doc_ids=split_doc_ids,
                new_summary=payload_data.get("new_summary"),
                new_lane=payload_data.get("new_lane"),
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
        merge_payload = {
            "split": True,
            "source_event_id": split_result.source_event_id,
            "new_event_id": split_result.new_event_id,
            "moved_docs": split_result.moved_docs,
            "remaining_docs": split_result.remaining_docs,
        }
        if split_result.new_event_id:
            rescore_event_ids.add(int(event_id))
            rescore_event_ids.add(int(split_result.new_event_id))

    await db.commit()
    if state_changed:
        celery.send_task(
            "app.workers.alerts.run_alerts",
            args=[event_id, {"score": float(event.score_plantao or 0.0), "reasons": ["FEEDBACK_STATE_TRANSITION", action]}, {}],
            queue="alerts",
        )
    for rescore_event_id in sorted(rescore_event_ids):
        celery.send_task(
            "app.workers.score.run_scoring",
            args=[rescore_event_id],
            queue="score",
        )
    logger.info(f"Feedback recorded for event {event_id}: {action}")
    return FeedbackActionResponse(
        status="recorded",
        event_id=event_id,
        action=action,
        state_changed=state_changed,
        merge=merge_payload,
    )
