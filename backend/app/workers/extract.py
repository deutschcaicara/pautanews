"""Extraction worker — uses trafilatura and feedparser.

Implements Blueprint §9.1 step 2.
"""
from __future__ import annotations

import logging
import trafilatura
import feedparser
from typing import Any, Dict

from app.celery_app import celery
from app.schemas.source_profile import SourceProfile, StrategyType

logger = logging.getLogger(__name__)

@celery.task(name="app.workers.extract.run_extraction")
def run_extraction(profile_dict: Dict[str, Any], raw_body: str, content_hash: str):
    """Clean text using trafilatura and prepare for anchor extraction."""
    profile = SourceProfile(**profile_dict)
    logger.info(f"Extracting content for {profile.source_id}")

    # 1. Extraction strategy based on profile
    items_to_process = [] # List of (text, url, title)

    if profile.strategy == StrategyType.RSS:
        feed = feedparser.parse(raw_body)
        if not feed.entries:
            logger.warning(f"Feedparser yielded no entries for {profile.source_id}")
            return
            
        logger.info(f"RSS capture detected {len(feed.entries)} entries for {profile.source_id}")
        for entry in feed.entries:
            # For RSS, we take the summary or content as text
            content = entry.get("summary") or entry.get("description") or ""
            items_to_process.append({
                "text": content,
                "url": entry.get("link"),
                "title": entry.get("title")
            })
    else:
        # Trafilatura extraction for HTML/SPA
        extracted = trafilatura.extract(
            raw_body, 
            include_comments=False,
            include_tables=True,
            no_fallback=False
        )
        if extracted:
            items_to_process.append({
                "text": extracted,
                "url": profile.endpoints.get("feed") or profile.endpoints.get("latest"),
                "title": None
            })
    
    if not items_to_process:
        logger.warning(f"Extraction yielded no items for {profile.source_id} (Strategy: {profile.strategy})")
        return

    # 2. Trigger Document versioning & Anchor extraction (M4)
    logger.info(f"Extraction successful ({len(items_to_process)} items). Fanning out to organization.")
    
    for item in items_to_process:
        celery.send_task(
            "app.workers.organize.run_organization",
            args=[profile.model_dump(), item["text"], content_hash, item["url"], item["title"]],
            queue="organize"
        )
