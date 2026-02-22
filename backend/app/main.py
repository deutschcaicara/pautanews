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
from starlette.responses import PlainTextResponse, Response, HTMLResponse
from sqlalchemy import select, func
from app.db import async_session_factory
from app.models.source import Source
from app.models.event import Event, EventStatus
from app.models.document import Document

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
    title="Radar de Pautas",
    version="0.1.0",
    description="Motor de radar de pautas para redações — Plantão + Oceano Azul",
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


# ─── Dashboard ───
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """Painel de Controle Radar de Pautas."""
    async with async_session_factory() as session:
        sources_count = (await session.execute(select(func.count()).select_from(Source))).scalar() or 0
        events_hot = (await session.execute(select(func.count()).select_from(Event).where(Event.status == EventStatus.HOT))).scalar() or 0
        events_new = (await session.execute(select(func.count()).select_from(Event).where(Event.status == EventStatus.NEW))).scalar() or 0
        docs_count = (await session.execute(select(func.count()).select_from(Document))).scalar() or 0

    return f"""
    <!DOCTYPE html>
    <html lang="pt-br">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Radar de Pautas | Dashboard</title>
        <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap" rel="stylesheet">
        <style>
            :root {{
                --bg: #0f172a;
                --card: rgba(30, 41, 59, 0.7);
                --accent: #38bdf8;
                --text: #f8fafc;
                --subtext: #94a3b8;
                --success: #22c55e;
            }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Outfit', sans-serif;
                background: var(--bg);
                color: var(--text);
                min-height: 100vh;
                display: flex;
                flex-direction: column;
                align-items: center;
                padding: 40px 20px;
                background-image: radial-gradient(circle at 50% 50%, #1e293b 0%, #0f172a 100%);
            }}
            .container {{ max-width: 1000px; width: 100%; }}
            header {{ margin-bottom: 50px; text-align: center; }}
            h1 {{ font-size: 2.5rem; font-weight: 700; margin-bottom: 10px; color: var(--accent); letter-spacing: -1px; }}
            .pulse {{
                display: inline-flex;
                align-items: center;
                font-size: 0.9rem;
                color: var(--success);
                font-weight: 600;
                background: rgba(34, 197, 94, 0.1);
                padding: 5px 15px;
                border-radius: 20px;
                margin-top: 10px;
            }}
            .pulse-dot {{
                width: 10px; height: 10px; background: var(--success);
                border-radius: 50%; margin-right: 10px;
                box-shadow: 0 0 0 rgba(34, 197, 94, 0.4);
                animation: pulse 2s infinite;
            }}
            @keyframes pulse {{
                0% {{ box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }}
                70% {{ box-shadow: 0 0 0 10px rgba(34, 197, 94, 0); }}
                100% {{ box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }}
            }}
            .grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
                gap: 20px;
                margin-top: 40px;
            }}
            .card {{
                background: var(--card);
                backdrop-filter: blur(10px);
                border: 1px solid rgba(255, 255, 255, 0.1);
                padding: 30px;
                border-radius: 20px;
                text-align: center;
                transition: transform 0.3s ease, border-color 0.3s ease;
            }}
            .card:hover {{ transform: translateY(-5px); border-color: var(--accent); }}
            .card .val {{ font-size: 3rem; font-weight: 700; color: var(--text); display: block; }}
            .card .lab {{ color: var(--subtext); text-transform: uppercase; font-size: 0.75rem; letter-spacing: 2px; margin-top: 5px; }}
            .links {{
                margin-top: 60px;
                display: flex;
                justify-content: center;
                gap: 20px;
            }}
            .btn {{
                padding: 12px 25px;
                border-radius: 12px;
                text-decoration: none;
                color: #fff;
                font-weight: 600;
                font-size: 0.9rem;
                background: rgba(255, 255, 255, 0.05);
                border: 1px solid rgba(255, 255, 255, 0.1);
                transition: all 0.3s ease;
            }}
            .btn:hover {{ background: var(--accent); color: var(--bg); transform: scale(1.05); }}
            .footer {{ margin-top: auto; padding-top: 60px; color: var(--subtext); font-size: 0.8rem; opacity: 0.5; }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>Radar de Pautas</h1>
                <div class="pulse">
                    <div class="pulse-dot"></div>
                    SISTEMA ONLINE & MONITORANDO
                </div>
            </header>

            <div class="grid">
                <div class="card">
                    <span class="val">{sources_count}</span>
                    <span class="lab">Fontes Ativas</span>
                </div>
                <div class="card">
                    <span class="val" style="color: #fca311;">{events_new}</span>
                    <span class="lab">Sugestões de Pauta</span>
                </div>
                <div class="card">
                    <span class="val" style="color: #ef4444;">{events_hot}</span>
                    <span class="lab">Pautas Quentes (HOT)</span>
                </div>
                <div class="card">
                    <span class="val">{docs_count}</span>
                    <span class="lab">Docs Coletados</span>
                </div>
            </div>

            <div class="links">
                <a href="/docs" class="btn">Documentação API</a>
                <a href="/health" class="btn">Health Check</a>
                <a href="/metrics" class="btn">Métricas de Performance</a>
            </div>
        </div>
        <footer class="footer">
            Inteligência Editorial para Redações | v0.1.0-MVP
        </footer>
    </body>
    </html>
    """


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
