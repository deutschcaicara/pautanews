"""FastAPI application — health, metrics, CORS, SSE stub."""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    generate_latest,
    multiprocess,
)
from starlette.responses import PlainTextResponse, Response

from app.config import settings
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — setup / teardown."""
    setup_logging()
    logger.info("Radar Hard News API starting", extra={"env": settings.APP_ENV})
    yield
    logger.info("Radar Hard News API shutting down")


app = FastAPI(
    title="Radar Hard News",
    version="0.1.0",
    description="Async investigative journalism radar — Plantão + Oceano Azul",
    lifespan=lifespan,
)

# ── CORS ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.APP_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


from app.api.feedback import router as feedback_router

app.include_router(feedback_router)


# ── Health ──
@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "service": "radar-hard-news"}


# ── Prometheus Metrics ──
@app.get("/metrics", tags=["ops"])
async def metrics() -> Response:
    """Prometheus scrape endpoint."""
    try:
        registry = CollectorRegistry()
        multiprocess.MultiProcessCollector(registry)
        data = generate_latest(registry)
    except ValueError:
        # Not running in multiprocess mode
        data = generate_latest()
    return PlainTextResponse(content=data, media_type=CONTENT_TYPE_LATEST)


# ── SSE placeholder (expanded in M3) ──
@app.get("/events/stream", tags=["sse"])
async def sse_stream() -> PlainTextResponse:
    """SSE endpoint stub — implemented in M3."""
    return PlainTextResponse(
        content="event: ping\ndata: {}\n\n",
        media_type="text/event-stream",
    )
