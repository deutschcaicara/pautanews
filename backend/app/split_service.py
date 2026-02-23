"""Editorial split helpers (MVP).

Creates a new event from selected docs of an existing event.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.event_state_service import ensure_event_has_initial_state, transition_event_status
from app.models.event import Event, EventDoc, EventStatus


@dataclass(slots=True)
class SplitResult:
    split: bool
    source_event_id: int
    new_event_id: int | None = None
    moved_docs: int = 0
    remaining_docs: int = 0


def _status_name(value: EventStatus | str) -> str:
    if isinstance(value, EventStatus):
        return value.value
    raw = str(value)
    if raw.startswith("EventStatus."):
        return raw.split(".", 1)[1]
    return raw


def _normalize_doc_ids(doc_ids: Iterable[int | str]) -> list[int]:
    out: list[int] = []
    seen: set[int] = set()
    for value in doc_ids:
        try:
            n = int(value)
        except Exception:
            continue
        if n <= 0 or n in seen:
            continue
        seen.add(n)
        out.append(n)
    return out


def _ensure_single_primary(rels: list[EventDoc]) -> None:
    if not rels:
        return
    primaries = [rel for rel in rels if bool(rel.is_primary)]
    if primaries:
        keep = primaries[0]
        for rel in primaries[1:]:
            rel.is_primary = False
        keep.is_primary = True
        return
    rels.sort(key=lambda r: (r.seen_at or datetime.now(timezone.utc), r.doc_id))
    rels[0].is_primary = True


async def split_event_by_docs(
    session: AsyncSession,
    *,
    source_event: Event,
    doc_ids: Iterable[int | str],
    new_summary: str | None = None,
    new_lane: str | None = None,
) -> SplitResult:
    """Move selected docs from `source_event` to a new event (MVP editorial split)."""
    if source_event.canonical_event_id:
        raise ValueError(f"Source event {source_event.id} is tombstoned into {source_event.canonical_event_id}")
    if _status_name(source_event.status) == EventStatus.MERGED.value:
        raise ValueError(f"Source event {source_event.id} is already MERGED")

    target_doc_ids = _normalize_doc_ids(doc_ids)
    if not target_doc_ids:
        raise ValueError("SPLIT requires payload.doc_ids")

    all_rels = (
        await session.execute(
            select(EventDoc)
            .where(EventDoc.event_id == source_event.id)
            .order_by(EventDoc.seen_at.asc(), EventDoc.doc_id.asc())
        )
    ).scalars().all()
    if len(all_rels) < 2:
        raise ValueError("Cannot split an event with less than 2 docs")

    target_rels = [rel for rel in all_rels if int(rel.doc_id) in set(target_doc_ids)]
    if not target_rels:
        raise ValueError("None of payload.doc_ids belong to the source event")
    if len(target_rels) >= len(all_rels):
        raise ValueError("SPLIT must leave at least one document in the source event")

    source_remaining = [rel for rel in all_rels if rel not in target_rels]
    _ensure_single_primary(source_remaining)
    _ensure_single_primary(target_rels)

    source_seen_min = min((rel.seen_at for rel in source_remaining if rel.seen_at), default=datetime.now(timezone.utc))
    source_seen_max = max((rel.seen_at for rel in source_remaining if rel.seen_at), default=source_seen_min)
    split_seen_min = min((rel.seen_at for rel in target_rels if rel.seen_at), default=datetime.now(timezone.utc))
    split_seen_max = max((rel.seen_at for rel in target_rels if rel.seen_at), default=split_seen_min)

    new_event = Event(
        status=EventStatus.PARTIAL_ENRICH,
        summary=(new_summary or source_event.summary),
        lane=(new_lane or source_event.lane),
        score_plantao=0.0,
        flags_json=dict(source_event.flags_json or {}) or None,
        first_seen_at=split_seen_min,
        last_seen_at=split_seen_max,
    )
    session.add(new_event)
    await session.flush()
    await transition_event_status(
        session,
        event=new_event,
        new_status=EventStatus.PARTIAL_ENRICH,
        status_reason="EDITORIAL_SPLIT_CREATED",
        force_history=True,
    )

    await ensure_event_has_initial_state(session, event=source_event)
    source_event.first_seen_at = source_seen_min
    source_event.last_seen_at = source_seen_max
    source_event.updated_at = datetime.now(timezone.utc)
    await transition_event_status(
        session,
        event=source_event,
        new_status=EventStatus(_status_name(source_event.status)),
        status_reason="EDITORIAL_SPLIT_SOURCE_UPDATED",
        force_history=True,
    )

    for rel in target_rels:
        rel.event_id = new_event.id

    return SplitResult(
        split=True,
        source_event_id=source_event.id,
        new_event_id=new_event.id,
        moved_docs=len(target_rels),
        remaining_docs=len(source_remaining),
    )
