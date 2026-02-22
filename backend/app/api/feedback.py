"""Feedback API — Blueprint §8 / §13.1 / §18.

Captures editorial actions (merge, ignore, snooze) for backtesting.
"""
from __future__ import annotations

import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Dict, Any

from app.db import get_session
from app.models.feedback import FeedbackEvent
from app.models.event import Event, EventStatus

router = APIRouter(prefix="/feedback", tags=["editorial"])
logger = logging.getLogger(__name__)

@router.post("/{event_id}/action")
async def record_feedback(
    event_id: int,
    action: str,
    payload: Dict[str, Any],
    db: AsyncSession = Depends(get_session)
):
    """§18: Toda ação editorial gera feedback_event."""
    
    # Valid actions (§18)
    if action not in ["IGNORE", "SNOOZE", "PAUTAR", "MERGE", "SPLIT"]:
        raise HTTPException(status_code=400, detail="Invalid editorial action")

    # 1. Persist feedback event
    feedback = FeedbackEvent(
        event_id=event_id,
        action=action,
        payload_json=payload,
        actor=payload.get("user_id", "anonymous")
    )
    db.add(feedback)
    
    # 2. Update event state based on action (§13)
    # (Simple mapping for MVP)
    if action == "IGNORE":
        # Update event status to IGNORED
        pass

    await db.commit()
    logger.info(f"Feedback recorded for event {event_id}: {action}")
    return {"status": "recorded"}
