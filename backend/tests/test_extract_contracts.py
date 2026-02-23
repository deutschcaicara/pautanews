from __future__ import annotations

import json

from app.schemas.source_profile import SourceProfile
from app.workers.extract import _extract_api_items, _extract_xhr_json_blob


def _profile(strategy: str = "SPA_API", metadata: dict | None = None) -> SourceProfile:
    pool = "HEAVY_RENDER_POOL" if strategy == "SPA_API" else "FAST_POOL"
    return SourceProfile(
        id=1,
        source_id="api_test",
        source_domain="api.example.com",
        tier=1,
        is_official=True,
        lang="pt-BR",
        pool=pool,
        strategy=strategy,
        endpoints={"api": "https://api.example.com/v1/items"},
        headers={"User-Agent": "test"},
        cadence={"interval_seconds": 60},
        limits={"rate_limit_req_per_min": 10, "concurrency_per_domain": 1, "timeout_seconds": 10, "max_bytes": 500000},
        observability={"starvation_window_hours": 24, "yield_keys": [], "baseline_rolling": True},
        metadata=metadata or {},
    )


def test_extract_xhr_json_blob_parses_marked_section() -> None:
    body = "<html></html><!-- XHR_JSON_CAPTURE_START -->\n{\"a\":1}\n<!-- XHR_JSON_CAPTURE_END -->"
    assert _extract_xhr_json_blob(body) == '{"a":1}'


def test_extract_api_items_with_contract() -> None:
    profile = _profile(
        metadata={
            "spa_api_contract": {
                "items_path": "data.items",
                "text_fields": ["summary", "body"],
                "url_field": "link",
                "title_field": "title",
                "published_at_field": "published_at",
            }
        }
    )
    payload = {
        "data": {
            "items": [
                {
                    "title": "Licitação",
                    "summary": "Resumo curto",
                    "body": "Corpo detalhado",
                    "link": "https://example.com/a",
                    "published_at": "2026-02-22T10:00:00Z",
                }
            ]
        }
    }
    items = _extract_api_items(
        profile=profile,
        raw_body=json.dumps(payload),
        content_hash="root_hash",
        fetch_meta={"snapshot_id": 123},
    )
    assert len(items) == 1
    item = items[0]
    assert item["url"] == "https://example.com/a"
    assert item["title"] == "Licitação"
    assert "Resumo curto" in item["text"]
    assert "Corpo detalhado" in item["text"]
    assert item["doc_meta"]["snapshot_id"] == 123
    assert item["doc_meta"]["published_at"] is not None


def test_extract_api_items_fallbacks_without_contract() -> None:
    profile = _profile(strategy="API")
    payload = [{"id": 1, "text": "A"}, {"id": 2, "description": "B", "url": "https://example.com/b"}]
    items = _extract_api_items(
        profile=profile,
        raw_body=json.dumps(payload),
        content_hash="root_hash",
        fetch_meta={},
    )
    assert len(items) == 2
    assert all(i["content_hash"] for i in items)
    assert items[0]["url"] == "https://api.example.com/v1/items"
    assert items[1]["url"] == "https://example.com/b"
