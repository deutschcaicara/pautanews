"""Anchor extraction worker — Blueprint §4 / §10.

Persists anchors and evidence features for a document.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.celery_app import celery
from app.db import async_session_factory
from app.models.anchor import DocAnchor, DocEvidenceFeature
from app.regex_pack import extract_anchors, compute_evidence_score
from app.schemas.source_profile import SourceProfile

logger = logging.getLogger(__name__)

@celery.task(name="app.workers.anchors.run_anchor_extraction")
def run_anchor_extraction(profile_dict: Dict[str, Any], doc_id: int, text: str):
    """Extract and persist anchors for a document."""
    profile = SourceProfile(**profile_dict)
    logger.info(f"Extracting anchors for doc {doc_id} ({profile.source_id})")

    anchors = extract_anchors(text)
    evidence_score = compute_evidence_score(anchors)

    # 1. Persist anchors and features
    # 2. Trigger Scoring (M8)
    
    # Placeholder for M1 models interaction
    logger.info(f"Found {len(anchors)} anchors. Evidence score: {evidence_score}")
    
    celery.send_task(
        "app.workers.score.run_scoring",
        args=[doc_id, evidence_score], # Simplified for MVP
        queue="score"
    )
