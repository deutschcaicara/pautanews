"""Shared merge/canonicalization helpers.

Used by async canonicalization worker and manual editorial merge actions.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.event_state_service import transition_event_status
from app.metrics import MERGES_TOTAL
from app.models.event import Event, EventDoc, EventStatus
from app.models.merge import MergeAudit
from app.models.score import EventScore


@dataclass(slots=True)
class MergeResult:
    merged: bool
    from_event_id: int
    to_event_id: int
    moved_docs: int = 0
    deduped_docs: int = 0
    reason_code: str = "HARD_ANCHOR_MATCH"


async def merge_event_into(
    session: AsyncSession,
    *,
    absorbed_event: Event,
    canonical_event: Event,
    reason_code: str,
    status_reason: str,
    evidence_json: dict[str, Any] | None = None,
) -> MergeResult:
    """Merge `absorbed_event` into `canonical_event` (TOMBSTONE) with doc reassignment.

    This is an MVP-safe merge:
    - reassigns `event_docs` to canonical event
    - dedupes duplicate `(event_id, doc_id)` relations
    - keeps a single primary doc on canonical event
    - updates canonical timeline bounds
    - writes `merge_audit`
    """
    if absorbed_event.id == canonical_event.id:
        return MergeResult(False, absorbed_event.id, canonical_event.id, reason_code=reason_code)
    if absorbed_event.canonical_event_id and int(absorbed_event.canonical_event_id) == int(canonical_event.id):
        return MergeResult(False, absorbed_event.id, canonical_event.id, reason_code=reason_code)
    if canonical_event.canonical_event_id:
        raise ValueError(f"Canonical target {canonical_event.id} is already merged into {canonical_event.canonical_event_id}")

    duplicate_audit = (
        await session.execute(
            select(MergeAudit.id).where(
                MergeAudit.from_event_id == absorbed_event.id,
                MergeAudit.to_event_id == canonical_event.id,
                MergeAudit.reason_code == reason_code,
            ).limit(1)
        )
    ).scalar()
    if duplicate_audit:
        return MergeResult(False, absorbed_event.id, canonical_event.id, reason_code=reason_code)

    canonical_rels = (
        await session.execute(select(EventDoc).where(EventDoc.event_id == canonical_event.id))
    ).scalars().all()
    absorbed_rels = (
        await session.execute(
            select(EventDoc)
            .where(EventDoc.event_id == absorbed_event.id)
            .order_by(EventDoc.is_primary.desc(), EventDoc.seen_at.asc())
        )
    ).scalars().all()

    canonical_doc_ids = {rel.doc_id for rel in canonical_rels}
    canonical_has_primary = any(bool(rel.is_primary) for rel in canonical_rels)
    moved_docs = 0
    deduped_docs = 0
    promoted_rel: EventDoc | None = None

    for rel in absorbed_rels:
        if rel.doc_id in canonical_doc_ids:
            await session.delete(rel)
            deduped_docs += 1
            continue

        was_primary = bool(rel.is_primary)
        rel.event_id = canonical_event.id
        if was_primary and canonical_has_primary:
            rel.is_primary = False
        elif was_primary and not canonical_has_primary:
            canonical_has_primary = True
            promoted_rel = rel
        elif not canonical_has_primary and promoted_rel is None:
            # Fallback if absorbed event had no primary marked.
            rel.is_primary = True
            canonical_has_primary = True
            promoted_rel = rel

        canonical_doc_ids.add(rel.doc_id)
        moved_docs += 1

    if not canonical_has_primary:
        # Last-resort: promote the oldest canonical relation.
        maybe_rel = next(iter(canonical_rels), None)
        if maybe_rel is not None:
            maybe_rel.is_primary = True

    canonical_event.first_seen_at = min(
        canonical_event.first_seen_at or datetime.now(timezone.utc),
        absorbed_event.first_seen_at or datetime.now(timezone.utc),
    )
    canonical_event.last_seen_at = max(
        canonical_event.last_seen_at or canonical_event.first_seen_at,
        absorbed_event.last_seen_at or absorbed_event.first_seen_at,
    )
    canonical_event.updated_at = datetime.now(timezone.utc)

    # Conservative merge of summary/lane/flags: keep canonical unless missing, union flags.
    canonical_event.summary = canonical_event.summary or absorbed_event.summary
    canonical_event.lane = canonical_event.lane or absorbed_event.lane
    merged_flags = dict(canonical_event.flags_json or {})
    merged_flags.update(dict(absorbed_event.flags_json or {}))
    canonical_event.flags_json = merged_flags or None

    # Preserve strongest scores on canonical event row for feed ordering.
    canonical_event.score_plantao = max(float(canonical_event.score_plantao or 0.0), float(absorbed_event.score_plantao or 0.0))
    canonical_score = (
        await session.execute(select(EventScore).where(EventScore.event_id == canonical_event.id))
    ).scalar()
    absorbed_score = (
        await session.execute(select(EventScore).where(EventScore.event_id == absorbed_event.id))
    ).scalar()
    if canonical_score and absorbed_score:
        canonical_score.score_plantao = max(float(canonical_score.score_plantao or 0.0), float(absorbed_score.score_plantao or 0.0))
        canonical_score.score_oceano_azul = max(float(canonical_score.score_oceano_azul or 0.0), float(absorbed_score.score_oceano_azul or 0.0))
        if not canonical_score.reasons_json and absorbed_score.reasons_json:
            canonical_score.reasons_json = absorbed_score.reasons_json
    elif not canonical_score and absorbed_score:
        session.add(
            EventScore(
                event_id=canonical_event.id,
                score_plantao=float(absorbed_score.score_plantao or 0.0),
                score_oceano_azul=float(absorbed_score.score_oceano_azul or 0.0),
                reasons_json=absorbed_score.reasons_json,
            )
        )

    absorbed_event.canonical_event_id = canonical_event.id
    await transition_event_status(
        session,
        event=absorbed_event,
        new_status=EventStatus.MERGED,
        status_reason=status_reason,
    )

    session.add(
        MergeAudit(
            from_event_id=absorbed_event.id,
            to_event_id=canonical_event.id,
            reason_code=reason_code,
            evidence_json=(evidence_json or {})
            | {
                "moved_docs": moved_docs,
                "deduped_docs": deduped_docs,
            },
        )
    )
    MERGES_TOTAL.labels(reason_code=reason_code[:64]).inc()

    return MergeResult(
        merged=True,
        from_event_id=absorbed_event.id,
        to_event_id=canonical_event.id,
        moved_docs=moved_docs,
        deduped_docs=deduped_docs,
        reason_code=reason_code,
    )

