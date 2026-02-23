from datetime import datetime, timedelta, timezone

from app.scheduler import _is_due
from app.schemas.source_profile import SourceProfile


def _profile(interval_seconds: int | None = None, cron: str | None = None) -> SourceProfile:
    return SourceProfile(
        id=1,
        source_id="test_source",
        source_domain="example.com",
        tier=1,
        is_official=False,
        lang="pt-BR",
        pool="FAST_POOL",
        strategy="RSS",
        endpoints={"feed": "https://example.com/rss.xml"},
        headers={"User-Agent": "test"},
        cadence={"interval_seconds": interval_seconds, "cron": cron},
        limits={"rate_limit_req_per_min": 10, "concurrency_per_domain": 1, "timeout_seconds": 10, "max_bytes": 1024},
        observability={"starvation_window_hours": 24, "yield_keys": [], "baseline_rolling": True},
    )


def test_interval_due_when_never_fetched() -> None:
    p = _profile(interval_seconds=60)
    assert _is_due(p, None, datetime.now(timezone.utc)) is True


def test_interval_not_due_before_threshold() -> None:
    now = datetime.now(timezone.utc)
    p = _profile(interval_seconds=300)
    assert _is_due(p, now - timedelta(seconds=100), now) is False


def test_interval_due_after_threshold() -> None:
    now = datetime.now(timezone.utc)
    p = _profile(interval_seconds=300)
    assert _is_due(p, now - timedelta(seconds=301), now) is True

