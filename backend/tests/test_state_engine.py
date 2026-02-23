from datetime import datetime, timedelta, timezone

from app.models.event import Event, EventStatus
from app.state_engine import action_gating_decision, evaluate_state_transition


def _event(status: EventStatus) -> Event:
    e = Event()  # SQLAlchemy model instance without session is enough for unit logic
    e.id = 1
    e.status = status
    return e


def test_new_goes_to_hydrating() -> None:
    e = _event(EventStatus.NEW)
    assert evaluate_state_transition(e, current_pool="FAST_POOL") == EventStatus.HYDRATING


def test_hydrating_timeout_fast_goes_partial_enrich() -> None:
    e = _event(EventStatus.HYDRATING)
    started = datetime.now(timezone.utc) - timedelta(seconds=30)
    assert evaluate_state_transition(e, current_pool="FAST_POOL", hydration_start_at=started) == EventStatus.PARTIAL_ENRICH


def test_hydrating_no_timeout_stays_same() -> None:
    e = _event(EventStatus.HYDRATING)
    started = datetime.now(timezone.utc) - timedelta(seconds=2)
    assert evaluate_state_transition(e, current_pool="FAST_POOL", hydration_start_at=started) == EventStatus.HYDRATING


def test_action_gating_blocks_merge_while_hydrating_before_timeout() -> None:
    e = _event(EventStatus.HYDRATING)
    e.first_seen_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    allowed, reason = action_gating_decision(e, action="MERGE", current_pool="FAST_POOL")
    assert allowed is False
    assert reason == "ACTION_BLOCKED_HYDRATING"


def test_action_gating_allows_merge_after_hydrating_timeout() -> None:
    e = _event(EventStatus.HYDRATING)
    e.first_seen_at = datetime.now(timezone.utc) - timedelta(seconds=60)
    allowed, reason = action_gating_decision(e, action="MERGE", current_pool="FAST_POOL")
    assert allowed is True
    assert reason is None


def test_action_gating_blocks_actions_on_tombstone() -> None:
    e = _event(EventStatus.MERGED)
    allowed, reason = action_gating_decision(e, action="PAUTAR")
    assert allowed is False
    assert reason == "ACTION_BLOCKED_MERGED_TOMBSTONE"
