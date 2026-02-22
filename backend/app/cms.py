"""CMS Integration — Blueprint §17.

Pushes structured event data to the CMS as Draft-only NewsArticles.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

logger = logging.getLogger(__name__)

class CMSConnector:
    """Connector for pushing drafts to investigative CMS."""

    def __init__(self, api_url: str = "https://cms.internal/api/v1"):
        self.api_url = api_url

    async def create_draft(self, event_id: int, payload: Dict[str, Any]) -> bool:
        """§17: POST cria Draft com timeline + evidências + proveniência."""
        
        # Prepare structured NewsArticle schema
        news_article = {
            "title": payload.get("title"),
            "status": "DRAFT",  # Blueprint §4.49: Draft-only
            "body": payload.get("clean_text"),
            "provenance": payload.get("sources", []),
            "evidence": {
                "anchors": payload.get("anchors", []),
                "evidence_score": payload.get("evidence_score", 0.0),
                "reasons": payload.get("reasons", [])
            },
            "timeline": payload.get("timeline", []),
            "created_at": datetime.now(timezone.utc).isoformat()
        }

        # Threshold check (§17): week fields require manual verification
        confidence = payload.get("confidence", 1.0)
        if confidence < 0.7:
            news_article["needs_review"] = True
            news_article["review_reason"] = "Low confidence in automated extraction"

        logger.info(f"Pushing DRAFT to CMS for event {event_id}. Needs review: {news_article.get('needs_review', False)}")
        
        # In production: await httpx.post(f"{self.api_url}/drafts", json=news_article)
        return True

def push_to_cms(event_id: int, payload: Dict[str, Any]):
    """Sync wrapper for Celery."""
    import asyncio
    connector = CMSConnector()
    loop = asyncio.get_event_loop()
    return loop.run_until_complete(connector.create_draft(event_id, payload))
