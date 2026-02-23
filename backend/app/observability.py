"""Optional OpenTelemetry bootstrap (graceful no-op if deps missing)."""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def setup_opentelemetry(app=None) -> None:
    """Best-effort OTel setup for API process.

    Keeps runtime compatible when OpenTelemetry packages are absent.
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor, ConsoleSpanExporter
    except Exception as exc:
        logger.info("OpenTelemetry disabled (packages missing): %s", exc)
        return

    provider = trace.get_tracer_provider()
    if provider.__class__.__name__ != "ProxyTracerProvider":
        # Already initialized by another bootstrap.
        return

    tracer_provider = TracerProvider(
        resource=Resource.create({"service.name": "radar-de-pautas-api"})
    )
    tracer_provider.add_span_processor(BatchSpanProcessor(ConsoleSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    if app is not None:
        try:
            from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

            FastAPIInstrumentor.instrument_app(app)
        except Exception as exc:
            logger.info("FastAPI OTel instrumentation unavailable: %s", exc)

    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception as exc:
        logger.info("HTTPX OTel instrumentation unavailable: %s", exc)

    try:
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        CeleryInstrumentor().instrument()
    except Exception as exc:
        logger.info("Celery OTel instrumentation unavailable: %s", exc)
