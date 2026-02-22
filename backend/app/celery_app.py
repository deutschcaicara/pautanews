"""Celery application — RabbitMQ broker, Redis result backend.

Queue layout follows Blueprint §7 (Pools / filas Celery).
"""
from __future__ import annotations

from celery import Celery
from kombu import Exchange, Queue

from app.config import settings

celery = Celery(
    "radar",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.REDIS_URL,
)

# ── Serialisation ──
celery.conf.accept_content = ["json"]
celery.conf.task_serializer = "json"
celery.conf.result_serializer = "json"
celery.conf.timezone = "UTC"
celery.conf.enable_utc = True

# ── Reliability ──
celery.conf.task_acks_late = True
celery.conf.worker_prefetch_multiplier = 1
celery.conf.task_reject_on_worker_lost = True

# ── Exchanges & Queues (Blueprint §7) ──
default_exchange = Exchange("radar", type="direct")

celery.conf.task_queues = (
    # Fast pool
    Queue("fetch_fast", default_exchange, routing_key="fetch_fast"),
    Queue("extract_fast", default_exchange, routing_key="extract_fast"),
    # Heavy render pool
    Queue("fetch_render", default_exchange, routing_key="fetch_render"),
    # Deep extract pool
    Queue("fetch_deep", default_exchange, routing_key="fetch_deep"),
    Queue("extract_deep", default_exchange, routing_key="extract_deep"),
    # Processing
    Queue("organize", default_exchange, routing_key="organize"),
    Queue("score", default_exchange, routing_key="score"),
    Queue("alerts", default_exchange, routing_key="alerts"),
    # Error handling
    Queue("retry", default_exchange, routing_key="retry"),
    Queue("dead_letter", default_exchange, routing_key="dead_letter"),
)

celery.conf.task_default_queue = "fetch_fast"
celery.conf.task_default_exchange = "radar"
celery.conf.task_default_routing_key = "fetch_fast"

# ── Task routes ──
celery.conf.task_routes = {
    "app.workers.fetch_fast.*": {"queue": "fetch_fast"},
    "app.workers.extract_fast.*": {"queue": "extract_fast"},
    "app.workers.fetch_render.*": {"queue": "fetch_render"},
    "app.workers.fetch_deep.*": {"queue": "fetch_deep"},
    "app.workers.extract_deep.*": {"queue": "extract_deep"},
    "app.workers.organize.*": {"queue": "organize"},
    "app.workers.score.*": {"queue": "score"},
    "app.workers.alerts.*": {"queue": "alerts"},
}

# ── Beat Schedule ──
celery.conf.beat_schedule = {
    "orchestrate-every-minute": {
        "task": "app.workers.orchestrate_fetches",
        "schedule": 60.0,
    },
}

# ── Auto-discover tasks ──
celery.autodiscover_tasks(["app.workers"], force=True)
