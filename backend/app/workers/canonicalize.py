"""Canonicalization worker for DEFER_MERGE -> MERGED/TOMBSTONE."""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.celery_app import celery
from app.db import async_session_factory
from app.merge_service import merge_event_into
from app.models.anchor import DocAnchor
from app.models.event import Event, EventDoc, EventStatus

logger = logging.getLogger(__name__)

STRONG_ANCHOR_TYPES = ("CNPJ", "CNJ", "PL", "SEI", "TCU")


@celery.task(name="app.workers.canonicalize.run_canonicalize")
def run_canonicalize() -> None:
    asyncio.run(_run_canonicalize())


async def _run_canonicalize() -> None:
    now = datetime.now(timezone.utc)
    merged_count = 0
    merged_alerts: list[tuple[int, int]] = []
    canonicals_to_rescore: set[int] = set()

    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(
                    Event.id,
                    Event.first_seen_at,
                    DocAnchor.anchor_type,
                    DocAnchor.anchor_value,
                )
                .join(EventDoc, EventDoc.event_id == Event.id)
                .join(DocAnchor, DocAnchor.doc_id == EventDoc.doc_id)
                .where(
                    Event.canonical_event_id.is_(None),
                    Event.status.notin_(
                        [
                            EventStatus.MERGED.value,
                            EventStatus.IGNORED.value,
                            EventStatus.EXPIRED.value,
                        ]
                    ),
                    Event.first_seen_at >= (now - timedelta(days=1)),
                    DocAnchor.anchor_type.in_(STRONG_ANCHOR_TYPES),
                )
            )
        ).all()

        by_anchor: dict[tuple[str, str], list[tuple[int, datetime]]] = defaultdict(list)
        for event_id, first_seen_at, anchor_type, anchor_value in rows:
            by_anchor[(str(anchor_type), str(anchor_value))].append((int(event_id), first_seen_at))

        seen_absorbed: set[int] = set()
        for (anchor_type, anchor_value), event_list in by_anchor.items():
            unique_events = {}
            for eid, seen_at in event_list:
                if eid not in unique_events or seen_at < unique_events[eid]:
                    unique_events[eid] = seen_at
            if len(unique_events) < 2:
                continue

            ordered = sorted(unique_events.items(), key=lambda x: (x[1], x[0]))
            canonical_event_id = ordered[0][0]
            for absorbed_event_id, _seen_at in ordered[1:]:
                if absorbed_event_id == canonical_event_id or absorbed_event_id in seen_absorbed:
                    continue

                absorbed_event = (
                    await session.execute(select(Event).where(Event.id == absorbed_event_id))
                ).scalar()
                canonical_event = (
                    await session.execute(select(Event).where(Event.id == canonical_event_id))
                ).scalar()
                if not absorbed_event or not canonical_event:
                    continue
                if absorbed_event.canonical_event_id:
                    continue

                merge_result = await merge_event_into(
                    session,
                    absorbed_event=absorbed_event,
                    canonical_event=canonical_event,
                    reason_code="HARD_ANCHOR_MATCH",
                    status_reason="HARD_ANCHOR_MATCH",
                    evidence_json={
                        "anchor_type": anchor_type,
                        "anchor_value": anchor_value,
                    },
                )
                if not merge_result.merged:
                    continue
                seen_absorbed.add(absorbed_event_id)
                merged_count += 1
                merged_alerts.append((absorbed_event_id, canonical_event_id))
                canonicals_to_rescore.add(canonical_event_id)

        await session.commit()

    if merged_count:
        logger.info("Canonicalization merged %s events", merged_count)
        for absorbed_event_id, canonical_event_id in merged_alerts:
            celery.send_task(
                "app.workers.alerts.run_alerts",
                args=[
                    absorbed_event_id,
                    {"score": 0.0, "reasons": ["EVENT_MERGED"]},
                    {"score": 0.0, "reasons": [f"CANONICAL:{canonical_event_id}"]},
                ],
                queue="alerts",
            )
        for canonical_event_id in sorted(canonicals_to_rescore):
            celery.send_task(
                "app.workers.score.run_scoring",
                args=[canonical_event_id],
                queue="score",
            )
