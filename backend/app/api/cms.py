"""CMS draft API (Draft-only)."""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cms import CMSConnector
from app.db import get_session
from app.models.anchor import DocAnchor
from app.models.document import Document
from app.models.entity_mention import EntityMention
from app.models.event import Event, EventDoc
from app.models.score import EventScore

router = APIRouter(prefix="/cms", tags=["cms"])


@router.post("/draft/{event_id}")
async def create_cms_draft(event_id: int, db: AsyncSession = Depends(get_session)) -> dict[str, Any]:
    event = (await db.execute(select(Event).where(Event.id == event_id))).scalar()
    if not event:
        raise HTTPException(status_code=404, detail="Event not found")
    if event.canonical_event_id:
        raise HTTPException(status_code=409, detail=f"Event merged into {event.canonical_event_id}")

    score_row = (await db.execute(select(EventScore).where(EventScore.event_id == event_id))).scalar()
    doc_rows = (
        await db.execute(
            select(Document, EventDoc)
            .join(EventDoc, EventDoc.doc_id == Document.id)
            .where(EventDoc.event_id == event_id)
            .order_by(EventDoc.seen_at.asc())
        )
    ).all()
    if not doc_rows:
        raise HTTPException(status_code=400, detail="Event has no documents")

    doc_ids = [doc.id for doc, _ in doc_rows]
    anchors = (
        await db.execute(select(DocAnchor).where(DocAnchor.doc_id.in_(doc_ids)))
    ).scalars().all()
    entities = (
        await db.execute(select(EntityMention).where(EntityMention.doc_id.in_(doc_ids)))
    ).scalars().all()

    sources_payload = []
    timeline = []
    for doc, rel in doc_rows:
        sources_payload.append(
            {
                "url": doc.url,
                "title": doc.title,
                "published_at": doc.published_at,
                "source_id": rel.source_id,
            }
        )
        timeline.append(
            {
                "doc_id": doc.id,
                "seen_at": rel.seen_at,
                "title": doc.title,
                "is_primary": rel.is_primary,
            }
        )

    anchor_payload = [
        {"type": a.anchor_type, "value": a.anchor_value, "doc_id": a.doc_id}
        for a in anchors
    ]

    # Conservative field confidence estimates (MVP). Can be replaced by richer heuristics later.
    field_confidence = {
        "person": 0.75 if any(e.label == "PER" for e in entities) else 1.0,
        "date": 0.85 if any(a.anchor_type == "DATA" for a in anchors) else 1.0,
        "value": 0.85 if any(a.anchor_type == "VALOR" for a in anchors) else 1.0,
        "org": 0.8 if any(e.label == "ORG" for e in entities) else 1.0,
    }

    primary_doc = next((doc for doc, rel in doc_rows if rel.is_primary), doc_rows[0][0])
    payload = {
        "title": event.summary or primary_doc.title or f"Draft Event #{event.id}",
        "clean_text": "\n\n".join([(doc.clean_text or "")[:3000] for doc, _ in doc_rows[:5]]),
        "sources": sources_payload,
        "anchors": anchor_payload,
        "evidence_score": float((score_row.score_oceano_azul if score_row else 0.0) or 0.0),
        "reasons": (score_row.reasons_json if score_row else {}) or {},
        "timeline": timeline,
        "confidence": 0.8,
        "field_confidence": field_confidence,
    }

    connector = CMSConnector()
    ok = await connector.create_draft(event_id, payload)
    return {
        "status": "draft_created" if ok else "draft_failed",
        "event_id": event_id,
        "payload_preview": {
            "title": payload["title"],
            "sources_count": len(sources_payload),
            "anchors_count": len(anchor_payload),
        },
    }

