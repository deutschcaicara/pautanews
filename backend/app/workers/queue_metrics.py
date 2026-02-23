"""Queue observability probe (best-effort).

Estimates queue backlog from Celery worker inspection snapshots and,
when available, RabbitMQ Management API.
"""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any

import httpx

from app.celery_app import celery
from app.config import settings
from app.metrics import QUEUE_BACKLOG_GAUGE

logger = logging.getLogger(__name__)


def _task_queue_name(task_payload: dict[str, Any]) -> str:
    delivery = task_payload.get("delivery_info") or {}
    queue = delivery.get("routing_key") or delivery.get("exchange") or task_payload.get("queue")
    if isinstance(queue, str) and queue:
        return queue
    return "unknown"


def _accumulate_snapshot(counter: Counter[str], rows: Any) -> None:
    if not isinstance(rows, dict):
        return
    for _worker, tasks in rows.items():
        if not isinstance(tasks, list):
            continue
        for item in tasks:
            payload = item if isinstance(item, dict) else {}
            # `scheduled()` may wrap the task under `request`.
            if "request" in payload and isinstance(payload["request"], dict):
                payload = payload["request"]
            counter[_task_queue_name(payload)] += 1


def _extract_queue_counts_from_management(payload: Any) -> Counter[str]:
    counts: Counter[str] = Counter()
    if not isinstance(payload, list):
        return counts
    for row in payload:
        if not isinstance(row, dict):
            continue
        name = str(row.get("name") or "unknown")
        # RabbitMQ queue API returns several counters. Use total messages if available.
        total = row.get("messages")
        if total is None:
            total = int(row.get("messages_ready") or 0) + int(row.get("messages_unacknowledged") or 0)
        try:
            counts[name] = max(0, int(total or 0))
        except Exception:
            continue
    return counts


def _rabbitmq_management_counts() -> Counter[str]:
    base = (settings.RABBITMQ_MANAGEMENT_URL or "").strip()
    if not base:
        return Counter()
    url = base.rstrip("/") + "/api/queues"
    auth = None
    if settings.RABBITMQ_MANAGEMENT_USER:
        auth = (settings.RABBITMQ_MANAGEMENT_USER, settings.RABBITMQ_MANAGEMENT_PASSWORD or "")
    try:
        resp = httpx.get(url, auth=auth, timeout=settings.RABBITMQ_MANAGEMENT_TIMEOUT_S)
        resp.raise_for_status()
        return _extract_queue_counts_from_management(resp.json())
    except Exception as exc:
        logger.info("RabbitMQ management queue probe unavailable: %s", exc)
        return Counter()


@celery.task(name="app.workers.queue_metrics.run_queue_metrics_probe")
def run_queue_metrics_probe() -> None:
    """Periodic best-effort queue backlog estimation via Celery inspect."""
    try:
        counts: Counter[str] = Counter()
        mgmt_counts = _rabbitmq_management_counts()
        if mgmt_counts:
            counts.update(mgmt_counts)
        else:
            inspector = celery.control.inspect(timeout=1.0)
            _accumulate_snapshot(counts, inspector.reserved() or {})
            _accumulate_snapshot(counts, inspector.active() or {})
            _accumulate_snapshot(counts, inspector.scheduled() or {})

        known_queues = {
            "fetch_fast",
            "fetch_render",
            "fetch_deep",
            "extract_fast",
            "extract_deep",
            "organize",
            "score",
            "alerts",
            "nlp",
            "retry",
            "dead_letter",
            "unknown",
        }
        for q in known_queues | set(counts.keys()):
            QUEUE_BACKLOG_GAUGE.labels(queue_name=q).set(float(counts.get(q, 0)))
    except Exception as exc:
        logger.warning("Queue metrics probe failed: %s", exc)
