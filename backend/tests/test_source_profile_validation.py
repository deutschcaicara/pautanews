from __future__ import annotations

import pytest

from app.schemas.source_profile import SourceProfile


def _base_profile(**overrides):
    payload = {
        "id": 1,
        "source_id": "senado_rss",
        "source_domain": "www12.senado.leg.br",
        "tier": 1,
        "is_official": True,
        "lang": "pt-BR",
        "pool": "FAST_POOL",
        "strategy": "RSS",
        "endpoints": {"feed": "https://www12.senado.leg.br/noticias/rss"},
        "headers": {"User-Agent": "RadarTest/1.0"},
        "cadence": {"interval_seconds": 60},
        "limits": {"rate_limit_req_per_min": 10, "concurrency_per_domain": 1, "timeout_seconds": 10, "max_bytes": 2048},
        "observability": {"starvation_window_hours": 24, "yield_keys": [], "baseline_rolling": True},
        "metadata": {},
    }
    payload.update(overrides)
    return payload


def test_rss_requires_feed_endpoint() -> None:
    with pytest.raises(ValueError):
        SourceProfile(**_base_profile(endpoints={"latest": "https://example.com/news"}))


def test_spa_api_requires_heavy_pool_and_contract() -> None:
    with pytest.raises(ValueError):
        SourceProfile(
            **_base_profile(
                pool="FAST_POOL",
                strategy="SPA_API",
                endpoints={"api": "https://api.example.com/items"},
                metadata={"spa_api_contract": {"items_path": "data.items"}},
            )
        )

    profile = SourceProfile(
        **_base_profile(
            pool="HEAVY_RENDER_POOL",
            strategy="SPA_API",
            endpoints={"api": "https://api.example.com/items"},
            metadata={
                "spa_api_contract": {"items_path": "data.items", "text_fields": ["body"]},
                "spa_api_request": {"method": "POST", "json": {"limit": 20}},
            },
        )
    )
    assert profile.strategy.value == "SPA_API"
    assert profile.pool.value == "HEAVY_RENDER_POOL"


def test_pdf_requires_deep_pool() -> None:
    with pytest.raises(ValueError):
        SourceProfile(
            **_base_profile(
                strategy="PDF",
                endpoints={"latest": "https://example.com/doc.pdf"},
                pool="FAST_POOL",
            )
        )

    p = SourceProfile(
        **_base_profile(
            strategy="PDF",
            endpoints={"latest": "https://example.com/doc.pdf"},
            pool="DEEP_EXTRACT_POOL",
        )
    )
    assert p.pool.value == "DEEP_EXTRACT_POOL"


def test_invalid_endpoint_scheme_rejected() -> None:
    with pytest.raises(ValueError):
        SourceProfile(**_base_profile(endpoints={"feed": "file:///tmp/feed.xml"}))


def test_cadence_requires_interval_or_cron() -> None:
    with pytest.raises(ValueError):
        SourceProfile(**_base_profile(cadence={}))

