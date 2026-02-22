"""Event Builder — Blueprint §9.1 and §11.

Creates or updates events based on semantic similarity or anchors.
For M3, we implement a lightweight upsert to meet the P95 ≤ 60s SLO.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict
from sqlalchemy import select

from app.celery_app import celery
from app.db import async_session_factory
from app.models.event import Event, EventStatus, EventDoc
from app.models.document import Document
from app.models.anchor import DocAnchor, DocEvidenceFeature
from app.schemas.source_profile import SourceProfile
from app.core.taxonomy import infer_editorial_lane, infer_source_class
from app.regex_pack import extract_anchors, compute_evidence_score

logger = logging.getLogger(__name__)

@celery.task(name="app.workers.organize.run_organization")
def run_organization(profile_dict: Dict[str, Any], clean_text: str, content_hash: str, url: str = None, title: str = None):
    """Lighweight Event Builder (Plantão Path)."""
    profile = SourceProfile(**profile_dict)
    logger.info(f"Organizing event for {profile.source_id} - URL: {url}")

    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(_persist_data(profile, clean_text, content_hash, url, title))

async def _persist_data(profile: SourceProfile, text: str, content_hash: str, url: str, title: str):
    async with async_session_factory() as session:
        # 1. Infer lane and class if not explicit
        lane = infer_editorial_lane(
            title=title,
            snippet=text[:500],
            editoria=profile.source_id # Use source_id as hint
        )

        # 2. Extract Anchors (T16.1)
        extracted_anchors = extract_anchors(text)
        evidence_score = compute_evidence_score(extracted_anchors)
        
        # 3. Upsert Document
        doc = Document(
            source_id=profile.id,
            title=title or f"Sugestão de Pauta: {profile.source_domain}",
            url=url or profile.endpoints.get("feed") or profile.endpoints.get("latest"),
            clean_text=text[:10000], # Increased for better analysis
            content_hash=content_hash
        )
        session.add(doc)
        await session.flush() # Get doc.id

        # 4. Filter & Persist DocAnchors
        anchor_objs = []
        for a in extracted_anchors:
            anchor_objs.append(DocAnchor(
                doc_id=doc.id,
                anchor_type=a["type"],
                anchor_value=a["value"],
                evidence_ptr=a["ptr"]
            ))
        session.add_all(anchor_objs)

        # 5. Persist Evidence Feature
        feature = DocEvidenceFeature(
            doc_id=doc.id,
            evidence_score=evidence_score,
            anchors_count=len(extracted_anchors),
            has_official_domain=profile.is_official
        )
        session.add(feature)

        # 6. Event Clustering (T16.2 - Basic Anchor-based)
        # Search for recent events (4h) that share any of these anchors
        target_event_id = None
        if extracted_anchors:
            # Simple heuristic: if any anchor value matches a recent one, join that event
            anchor_values = [a["value"] for a in extracted_anchors]
            stmt = select(DocAnchor.doc_id).where(
                DocAnchor.anchor_value.in_(anchor_values),
                DocAnchor.doc_id != doc.id
            ).limit(1)
            result = await session.execute(stmt)
            match_doc_id = result.scalar()
            
            if match_doc_id:
                # Find the event associated with this match
                stmt = select(EventDoc.event_id).where(EventDoc.doc_id == match_doc_id).limit(1)
                result = await session.execute(stmt)
                target_event_id = result.scalar()

        if target_event_id:
            logger.info(f"Clustering doc {doc.id} into existing event {target_event_id}")
            event_doc = EventDoc(
                event_id=target_event_id,
                doc_id=doc.id,
                source_id=profile.id,
                is_primary=False
            )
            session.add(event_doc)
        else:
            # Create new event
            status = EventStatus.NEW
            p_score = 50.0
            if profile.tier == 1:
                status = EventStatus.HOT
                p_score = 85.0

            event = Event(
                status=status,
                lane=lane,
                summary=title or f"Novo sinal de pauta em {profile.source_domain}",
                score_plantao=p_score
            )
            session.add(event)
            await session.flush() # Get event.id
            
            event_doc = EventDoc(
                event_id=event.id,
                doc_id=doc.id,
                source_id=profile.id,
                is_primary=True
            )
            session.add(event_doc)
            target_event_id = event.id

        await session.commit()
        logger.info(f"Organized doc {doc.id} -> Event {target_event_id}")

        # 7. Trigger Scoring Adjustment (T16.3)
        celery.send_task(
            "app.workers.score.run_scoring",
            args=[target_event_id],
            queue="score"
        )
