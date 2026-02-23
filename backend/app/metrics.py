"""Prometheus metrics for pipeline and product observability."""
from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram


FETCH_ATTEMPTS_TOTAL = Counter(
    "radar_fetch_attempts_total",
    "Total fetch attempts by outcome",
    ["source_id", "strategy", "pool", "status_class", "error_class"],
)

FETCH_LATENCY_SECONDS = Histogram(
    "radar_fetch_latency_seconds",
    "Fetch latency by strategy/pool",
    ["strategy", "pool"],
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20, 40, 60),
)

EXTRACT_ITEMS_TOTAL = Counter(
    "radar_extract_items_total",
    "Items produced by extraction",
    ["source_id", "strategy"],
)

ORGANIZER_DOCS_TOTAL = Counter(
    "radar_organizer_docs_total",
    "Documents organized into events",
    ["source_id", "lane", "matched_existing"],
)

ANCHOR_YIELD_TOTAL = Counter(
    "radar_anchor_yield_total",
    "Total anchors extracted by source",
    ["source_id"],
)

EVIDENCE_SCORE_OBS = Histogram(
    "radar_evidence_score",
    "Evidence score distribution",
    ["source_id"],
    buckets=(0, 0.5, 1, 2, 3, 5, 8, 12, 15),
)

EVENT_STATE_TRANSITIONS_TOTAL = Counter(
    "radar_event_state_transitions_total",
    "Event state transitions",
    ["from_status", "to_status", "reason"],
)

EVENT_SCORES_OBS = Histogram(
    "radar_event_score",
    "Event scores by lane",
    ["score_type", "lane"],
    buckets=(0, 5, 10, 20, 30, 40, 50, 60, 70, 80, 90, 100),
)

UNVERIFIED_VIRAL_EVENTS_TOTAL = Counter(
    "radar_unverified_viral_events_total",
    "Events flagged as UNVERIFIED_VIRAL",
    ["lane"],
)

MERGES_TOTAL = Counter(
    "radar_event_merges_total",
    "Merged events (tombstones)",
    ["reason_code"],
)

QUEUE_BACKLOG_GAUGE = Gauge(
    "radar_queue_backlog_estimate",
    "Queue backlog estimate (manual / optional)",
    ["queue_name"],
)

DATA_STARVATION_INCIDENTS_TOTAL = Counter(
    "radar_data_starvation_incidents_total",
    "DATA_STARVATION incidents",
    ["source_domain"],
)

SSE_EVENTS_SENT_TOTAL = Counter(
    "radar_sse_events_sent_total",
    "SSE events sent by type",
    ["event_type"],
)

