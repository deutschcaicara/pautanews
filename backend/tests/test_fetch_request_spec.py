from __future__ import annotations

from app.schemas.source_profile import SourceProfile
from app.workers.fetch import _prepare_request_spec


def _profile(metadata: dict | None = None) -> SourceProfile:
    return SourceProfile(
        id=1,
        source_id="spa_api_test",
        source_domain="api.example.com",
        tier=1,
        is_official=True,
        lang="pt-BR",
        pool="FAST_POOL",
        strategy="SPA_API",
        endpoints={"api": "https://api.example.com/v1/items"},
        headers={"User-Agent": "RadarTest/1.0"},
        cadence={"interval_seconds": 60},
        limits={"rate_limit_req_per_min": 10, "concurrency_per_domain": 1, "timeout_seconds": 10, "max_bytes": 100000},
        observability={"starvation_window_hours": 24, "yield_keys": [], "baseline_rolling": True},
        metadata=metadata or {},
    )


def test_prepare_request_spec_defaults_to_get() -> None:
    spec = _prepare_request_spec(_profile(), {"User-Agent": "U"})
    assert spec["url"] == "https://api.example.com/v1/items"
    assert spec["method"] == "GET"
    assert spec["params"] is None
    assert spec["headers"]["User-Agent"] == "U"


def test_prepare_request_spec_applies_spa_api_request_overrides() -> None:
    spec = _prepare_request_spec(
        _profile(
            metadata={
                "spa_api_request": {
                    "url": "https://api.example.com/v2/search",
                    "method": "POST",
                    "params": {"page": 2},
                    "json": {"query": "licitacao"},
                    "headers": {"X-Token": "abc"},
                }
            }
        ),
        {"User-Agent": "U"},
    )
    assert spec["url"] == "https://api.example.com/v2/search"
    assert spec["method"] == "POST"
    assert spec["params"] == {"page": 2}
    assert spec["json"] == {"query": "licitacao"}
    assert spec["headers"]["X-Token"] == "abc"
    assert spec["headers"]["User-Agent"] == "U"

