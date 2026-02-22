"""Extraction worker — uses trafilatura for boilerplate removal.

Implements Blueprint §9.1 step 2.
"""
from __future__ import annotations

import logging
import trafilatura
from typing import Any, Dict

from app.celery_app import celery
from app.schemas.source_profile import SourceProfile

logger = logging.getLogger(__name__)

@celery.task(name="app.workers.extract.run_extraction")
def run_extraction(profile_dict: Dict[str, Any], raw_body: str, content_hash: str):
    """Clean text using trafilatura and prepare for anchor extraction."""
    profile = SourceProfile(**profile_dict)
    logger.info(f"Extracting content for {profile.source_id}")

    # 1. Trafilatura extraction
    extracted = trafilatura.extract(
        raw_body, 
        include_comments=False,
        include_tables=True,
        no_fallback=False
    )
    
    if not extracted:
        logger.warning(f"Trafilatura yielded no text for {profile.source_id}")
        return

    # 2. Trigger Document versioning & Anchor extraction (M4)
    logger.info(f"Extraction successful ({len(extracted)} chars). Fanning out to anchors.")
    
    # Placeholder for M4/M7
    celery.send_task(
        "app.workers.organize.run_organization",
        args=[profile.model_dump(), extracted, content_hash],
        queue="organize"
    )
