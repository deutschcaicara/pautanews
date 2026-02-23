from __future__ import annotations

from app.workers.queue_metrics import _extract_queue_counts_from_management


def test_extract_queue_counts_from_management_parses_message_counts() -> None:
    payload = [
        {"name": "fetch_fast", "messages": 12},
        {"name": "dead_letter", "messages_ready": 3, "messages_unacknowledged": 2},
        {"name": "bad", "messages": "x"},
    ]
    counts = _extract_queue_counts_from_management(payload)
    assert counts["fetch_fast"] == 12
    assert counts["dead_letter"] == 5
    assert "bad" not in counts

