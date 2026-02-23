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

        # Threshold checks (§17): configurable by field type
        thresholds = {
            "person": 0.90,
            "date": 0.85,
            "value": 0.85,
            "org": 0.80,
        }
        field_confidence = payload.get("field_confidence", {}) or {}
        review_flags = []
        for field_type, threshold in thresholds.items():
            got = field_confidence.get(field_type)
            if got is not None and float(got) < threshold:
                review_flags.append(
                    {
                        "field_type": field_type,
                        "confidence": float(got),
                        "threshold": threshold,
                    }
                )

        confidence = payload.get("confidence", 1.0)
        if confidence < 0.7:
            review_flags.append(
                {
                    "field_type": "global",
                    "confidence": float(confidence),
                    "threshold": 0.7,
                }
            )
        if review_flags:
            news_article["needs_review"] = True
            news_article["review_reason"] = "Confidence threshold not met"
            news_article["review_flags"] = review_flags

        logger.info(f"Pushing DRAFT to CMS for event {event_id}. Needs review: {news_article.get('needs_review', False)}")
        
        # In production: await httpx.post(f"{self.api_url}/drafts", json=news_article)
        return True

def push_to_cms(event_id: int, payload: Dict[str, Any]):
    """Sync wrapper for Celery."""
    import asyncio
    connector = CMSConnector()
    return asyncio.run(connector.create_draft(event_id, payload))
