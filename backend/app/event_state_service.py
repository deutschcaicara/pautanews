"""Event state transition persistence helpers.

Centralizes updates to `events.status` and `event_state` history rows.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.metrics import EVENT_STATE_TRANSITIONS_TOTAL
from app.models.event import Event, EventState, EventStatus


def _status_value(value: EventStatus | str) -> str:
    if isinstance(value, EventStatus):
        return value.value
    return str(value)


async def append_event_state(
    session: AsyncSession,
    *,
    event_id: int,
    new_status: EventStatus,
    status_reason: str | None = None,
) -> EventState:
    row = EventState(
        event_id=event_id,
        status=new_status,
        status_reason=status_reason,
        updated_at=datetime.now(timezone.utc),
    )
    session.add(row)
    return row


async def transition_event_status(
    session: AsyncSession,
    *,
    event: Event,
    new_status: EventStatus,
    status_reason: str | None = None,
    force_history: bool = False,
) -> bool:
    """Update event status and append history row.

    Returns `True` when status changed (or `force_history` is set), else `False`.
    """
    old_status = _status_value(event.status)
    changed = old_status != _status_value(new_status)
    if not changed and not force_history:
        return False

    event.status = new_status
    event.updated_at = datetime.now(timezone.utc)
    await append_event_state(
        session,
        event_id=event.id,
        new_status=new_status,
        status_reason=status_reason,
    )
    EVENT_STATE_TRANSITIONS_TOTAL.labels(
        from_status=old_status,
        to_status=_status_value(new_status),
        reason=(status_reason or "UNKNOWN")[:64],
    ).inc()
    return True


async def ensure_event_has_initial_state(
    session: AsyncSession,
    *,
    event: Event,
    fallback_reason: str = "INITIAL_STATE_BACKFILL",
) -> bool:
    existing = (
        await session.execute(
            select(EventState.id).where(EventState.event_id == event.id).limit(1)
        )
    ).scalar()
    if existing:
        return False
    await append_event_state(
        session,
        event_id=event.id,
        new_status=EventStatus(_status_value(event.status)),
        status_reason=fallback_reason,
    )
    return True
