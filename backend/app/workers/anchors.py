"""Anchor extraction worker — deprecated placeholder.

The current pipeline persists anchors in organizer.py. This task remains
registered only for backward compatibility and must not call score with an
invalid signature.
"""
from __future__ import annotations

import logging
from typing import Any, Dict

from app.celery_app import celery
from app.regex_pack import extract_anchors, compute_evidence_score
from app.schemas.source_profile import SourceProfile

logger = logging.getLogger(__name__)

@celery.task(name="app.workers.anchors.run_anchor_extraction")
def run_anchor_extraction(profile_dict: Dict[str, Any], doc_id: int, text: str):
    """Deprecated compatibility task (no persistence in current pipeline)."""
    profile = SourceProfile(**profile_dict)
    logger.info(f"Extracting anchors for doc {doc_id} ({profile.source_id})")

    anchors = extract_anchors(text)
    evidence_score = compute_evidence_score(anchors)

    # NOTE: organizer.py already persists anchors/features and triggers scoring.
    # Keep this task as a safe no-op to avoid runtime signature mismatches if
    # an old dispatch path is still active.
    logger.info(f"Found {len(anchors)} anchors. Evidence score: {evidence_score}")
    return
