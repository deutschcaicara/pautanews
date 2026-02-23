"""Event Builder — Blueprint §9.1 and §11.

Creates or updates events based on semantic similarity or anchors.
Implements versioning and Defer Merge logic.
"""
from __future__ import annotations

import asyncio
import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Any, Dict
from sqlalchemy import select, desc, tuple_, or_

from app.celery_app import celery
from app.db import async_session_factory
from app.event_state_service import ensure_event_has_initial_state, transition_event_status
from app.health import yield_monitor, trigger_starvation_incident
from app.metrics import ANCHOR_YIELD_TOTAL, EVIDENCE_SCORE_OBS, ORGANIZER_DOCS_TOTAL
from app.models.event import Event, EventStatus, EventDoc
from app.models.document import Document
from app.models.anchor import DocAnchor, DocEvidenceFeature
from app.models.entity_mention import EntityMention
from app.schemas.source_profile import SourceProfile
from app.core.taxonomy import infer_editorial_lane
from app.core.similarity import compute_simhash64, hamming_distance64
from app.regex_pack import extract_anchors, compute_evidence_score

logger = logging.getLogger(__name__)


def _parse_optional_dt(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        pass
    try:
        parsed = parsedate_to_datetime(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except Exception:
        return None


def _coerce_optional_int(value: Any) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except Exception:
        return None

@celery.task(name="app.workers.organize.run_organization")
def run_organization(
    profile_dict: Dict[str, Any],
    clean_text: str,
    content_hash: str,
    url: str = None,
    title: str = None,
    doc_meta: Dict[str, Any] | None = None,
):
    """Event Builder with Versioning and Defer Merge support."""
    profile = SourceProfile(**profile_dict)
    logger.info(f"Organizing document for {profile.source_id} - URL: {url}")

    asyncio.run(_process_document_and_event(profile, clean_text, content_hash, url, title, doc_meta or {}))

async def _process_document_and_event(
    profile: SourceProfile,
    text: str,
    content_hash: str,
    url: str,
    title: str,
    doc_meta: Dict[str, Any] | None = None,
):
    source_pk = profile.id
    if source_pk is None:
        logger.error("Organizer aborted: SourceProfile missing database id for %s", profile.source_id)
        return
    doc_meta = dict(doc_meta or {})
    canonical_url_hint = (
        str(doc_meta.get("canonical_url")).strip()[:2048]
        if doc_meta.get("canonical_url")
        else None
    )

    async with async_session_factory() as session:
        # 1. Versioning Check (Blueprint §8)
        if canonical_url_hint and canonical_url_hint != url:
            stmt = (
                select(Document)
                .where(or_(Document.url == url, Document.canonical_url == canonical_url_hint))
                .order_by(desc(Document.version_no))
                .limit(1)
            )
        else:
            stmt = select(Document).where(Document.url == url).order_by(desc(Document.version_no)).limit(1)
        result = await session.execute(stmt)
        existing_doc = result.scalar()
        
        version_no = 1
        if existing_doc:
            if existing_doc.content_hash == content_hash:
                logger.info(f"Document {url} already exists with same hash. Skipping.")
                return
            version_no = existing_doc.version_no + 1
            logger.info(f"New version ({version_no}) detected for {url}")

        # 2. Extract intelligence
        shash = compute_simhash64(text)
        editoria_hint = None
        if isinstance(profile.metadata, dict):
            editoria_hint = profile.metadata.get("legacy_editoria") or profile.metadata.get("editoria")
        lane = infer_editorial_lane(
            title=(title or doc_meta.get("title")),
            snippet=text[:500],
            editoria=editoria_hint,
        )
        extracted_anchors = extract_anchors(text)
        evidence_score = compute_evidence_score(extracted_anchors)
        yield_monitor.update_yield(source_pk, len(extracted_anchors), status_code=200)
        if profile.is_official and yield_monitor.check_starvation(
            source_pk,
            calendar_profile=(profile.observability.calendar_profile if profile.observability else None),
        ):
            trigger_starvation_incident(source_pk, profile.source_domain or profile.source_id)
        ANCHOR_YIELD_TOTAL.labels(source_id=str(profile.source_id)).inc(len(extracted_anchors))
        EVIDENCE_SCORE_OBS.labels(source_id=str(profile.source_id)).observe(float(evidence_score))
        
        # 3. Create Document
        doc_published_at = _parse_optional_dt(doc_meta.get("published_at"))
        doc_modified_at = _parse_optional_dt(doc_meta.get("modified_at"))
        doc_author = str(doc_meta.get("author")).strip()[:512] if doc_meta.get("author") else None
        doc_lang = str(doc_meta.get("lang") or profile.lang)[:8] if (doc_meta.get("lang") or profile.lang) else None
        canonical_url = str(canonical_url_hint or url)[:2048] if (canonical_url_hint or url) else None
        snapshot_id = _coerce_optional_int(doc_meta.get("snapshot_id"))
        doc = Document(
            source_id=source_pk,
            title=(title or doc_meta.get("title") or f"Sinal: {profile.source_domain}"),
            url=url,
            canonical_url=canonical_url,
            author=doc_author,
            published_at=doc_published_at,
            modified_at=doc_modified_at,
            clean_text=text[:20000],
            lang=doc_lang,
            content_hash=content_hash,
            simhash=shash,
            version_no=version_no,
            snapshot_id=snapshot_id,
        )
        session.add(doc)
        await session.flush() # Get doc.id

        # 4. Persist Anchors & Features
        anchor_objs = [
            DocAnchor(doc_id=doc.id, anchor_type=a["type"], anchor_value=a["value"], evidence_ptr=a["ptr"])
            for a in extracted_anchors
        ]
        session.add_all(anchor_objs)

        # Minimal entity mentions from deterministic anchors (improvable later).
        entity_label_map = {
            "CNPJ": "ORG",
            "CPF": "PER",
            "CNJ": "GOV",
            "SEI": "GOV",
            "TCU": "GOV",
            "PL": "EVENT",
            "ATO": "GOV",
        }
        entity_mentions = [
            EntityMention(
                doc_id=doc.id,
                entity_key=f"{a['type']}:{a['value']}",
                label=entity_label_map.get(a["type"], "EVENT"),
                span_json=None,
                evidence_ptr=a.get("ptr"),
                confidence=1.0,
            )
            for a in extracted_anchors
            if a["type"] in entity_label_map
        ]
        if entity_mentions:
            session.add_all(entity_mentions)

        anchor_type_counts = Counter(a["type"] for a in extracted_anchors)
        has_pdf = bool(
            (url or "").lower().endswith(".pdf")
            or anchor_type_counts.get("PDF", 0) > 0
        )
        money_count = int(anchor_type_counts.get("VALOR", 0))
        has_table_like = ("[TABLE]" in text) or (" | " in text and text.count("\n") >= 2)
        
        feature = DocEvidenceFeature(
            doc_id=doc.id,
            evidence_score=evidence_score,
            has_pdf=has_pdf,
            anchors_count=len(extracted_anchors),
            has_official_domain=profile.is_official,
            money_count=money_count,
            has_table_like=has_table_like,
            evidence_json={
                "anchor_type_counts": dict(anchor_type_counts),
                "source_domain": profile.source_domain,
                "source_is_official": profile.is_official,
                "has_pdf": has_pdf,
                "has_table_like": has_table_like,
            },
        )
        session.add(feature)

        # 5. Defer Merge / Clustering Heuristic (Blueprint §11 & §13)
        target_event_id = None
        
        # Priority 1: Match by strong anchors (CNPJ, CNJ, PL) within 12h
        if extracted_anchors:
            strong_anchors = [
                (a["type"], a["value"])
                for a in extracted_anchors
                if a["type"] in ["CNPJ", "CNJ", "PL", "SEI"]
            ]
            if strong_anchors:
                stmt = (
                    select(EventDoc.event_id)
                    .join(DocAnchor, DocAnchor.doc_id == EventDoc.doc_id)
                    .where(
                        tuple_(DocAnchor.anchor_type, DocAnchor.anchor_value).in_(strong_anchors),
                        EventDoc.seen_at >= datetime.now(timezone.utc) - timedelta(hours=12)
                    )
                    .limit(1)
                )
                result = await session.execute(stmt)
                target_event_id = result.scalar()

        # Priority 2: Match existing document version to its event
        if not target_event_id and existing_doc:
            stmt = select(EventDoc.event_id).where(EventDoc.doc_id == existing_doc.id).limit(1)
            result = await session.execute(stmt)
            target_event_id = result.scalar()

        # Priority 3: Match by SimHash similarity (Hamming Distance <= 12)
        if not target_event_id and shash:
            # Query documents from the last 12h that have a simhash
            time_window = datetime.now(timezone.utc) - timedelta(hours=12)
            stmt = select(Document.id, Document.simhash).where(
                Document.created_at >= time_window,
                Document.simhash.is_not(None)
            )
            result = await session.execute(stmt)
            candidates = result.all()
            
            best_doc_id = None
            min_dist = 64
            for c_id, c_hash in candidates:
                dist = hamming_distance64(shash, c_hash)
                if dist <= 12 and dist < min_dist:
                    min_dist = dist
                    best_doc_id = c_id
            
            if best_doc_id:
                stmt = select(EventDoc.event_id).where(EventDoc.doc_id == best_doc_id).limit(1)
                result = await session.execute(stmt)
                target_event_id = result.scalar()
                if target_event_id:
                    logger.info(f"SIMILARITY_MATCH: Hamming dist {min_dist} found for Event {target_event_id}")

        # 6. Finalize Event Association
        if target_event_id:
            logger.info(f"DEFER_MERGE: Linking doc {doc.id} to Event {target_event_id}")
            target_event = (await session.execute(select(Event).where(Event.id == target_event_id))).scalar()
            if target_event:
                target_event.last_seen_at = datetime.now(timezone.utc)
                await ensure_event_has_initial_state(session, event=target_event)
            event_doc = EventDoc(
                event_id=target_event_id,
                doc_id=doc.id,
                source_id=source_pk,
                is_primary=False
            )
            session.add(event_doc)
            ORGANIZER_DOCS_TOTAL.labels(
                source_id=str(profile.source_id),
                lane=(lane or "geral"),
                matched_existing="true",
            ).inc()
        else:
            # Create new canonical event
            status = EventStatus.HYDRATING
            p_score = 40.0 # Base score
            
            # Tier-1 boost (Blueprint §12.1)
            if profile.tier == 1:
                p_score = 75.0
                
            event = Event(
                status=status,
                lane=lane,
                summary=title or f"Novo sinal em {profile.source_domain}",
                score_plantao=p_score,
                first_seen_at=datetime.now(timezone.utc),
                last_seen_at=datetime.now(timezone.utc)
            )
            session.add(event)
            await session.flush()
            await transition_event_status(
                session,
                event=event,
                new_status=EventStatus.HYDRATING,
                status_reason="FAST_PATH_EVENT_CREATED",
                force_history=True,
            )
            
            event_doc = EventDoc(
                event_id=event.id,
                doc_id=doc.id,
                source_id=source_pk,
                is_primary=True
            )
            session.add(event_doc)
            target_event_id = event.id
            ORGANIZER_DOCS_TOTAL.labels(
                source_id=str(profile.source_id),
                lane=(lane or "geral"),
                matched_existing="false",
            ).inc()

        await session.commit()
        
        # 7. Trigger Scoring Engine (Blueprint §12)
        celery.send_task(
            "app.workers.score.run_scoring",
            args=[target_event_id],
            queue="score"
        )
