from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone

from app.health import YieldMonitor


def _point(ts: datetime, anchors: int, status_code: int = 200) -> dict:
    return {
        "ts": ts.isoformat(),
        "anchors_count": anchors,
        "status_code": status_code,
    }


def test_starvation_detects_rolling_collapse() -> None:
    m = YieldMonitor()
    m._redis = None
    now = datetime.now(timezone.utc)
    source_id = 1
    rows = deque(maxlen=500)
    # historical healthy
    for i in range(20, 40):
        rows.append(_point(now - timedelta(minutes=i), anchors=3))
    # recent collapse with 200 OK
    for i in range(5):
        rows.append(_point(now - timedelta(minutes=i), anchors=0))
    m._baselines[source_id] = rows
    assert m.check_starvation(source_id, last_200_ok_window_mins=10) is True


def test_starvation_calendar_profile_uses_same_hour_baseline() -> None:
    m = YieldMonitor()
    m._redis = None
    now = datetime.now(timezone.utc)
    source_id = 2
    rows = deque(maxlen=500)
    # same hour historical points (older than current window)
    for days_back in range(8, 20):
        ts = (now - timedelta(days=days_back)).replace(minute=5, second=0, microsecond=0)
        rows.append(_point(ts, anchors=4))
    # add a lot of unrelated low-yield history at another hour so global rolling average stays <1
    for days_back in range(8, 120):
        ts = (now - timedelta(days=days_back)).replace(hour=(now.hour - 3) % 24, minute=10, second=0, microsecond=0)
        rows.append(_point(ts, anchors=0))
    # recent window with 200 OK and zero yield
    for i in range(6):
        rows.append(_point(now - timedelta(minutes=i), anchors=0))
    m._baselines[source_id] = rows
    assert m.check_starvation(source_id, last_200_ok_window_mins=10, calendar_profile="always_on") is True
