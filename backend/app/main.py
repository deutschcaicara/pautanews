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
from sqlalchemy import select, func, desc
from app.db import async_session_factory
from app.models.source import Source
from app.models.event import Event, EventStatus, EventDoc
from app.models.document import Document
from app.models.anchor import DocAnchor
from app.models.score import EventScore

from app.config import settings
from app.logging_config import setup_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — setup / teardown."""
    setup_logging()
    logger.info("Radar de Pautas API starting", extra={"env": settings.APP_ENV})
    yield
    logger.info("Radar de Pautas API shutting down")


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

# ── API ──
@app.get("/api/events", tags=["content"])
async def get_events(status: str | None = None, lane: str | None = None, limit: int = 20):
    """Retorna feed de eventos com âncoras e scores."""
    async with async_session_factory() as session:
        stmt = (
            select(Event, DocAnchor)
            .outerjoin(EventDoc, EventDoc.event_id == Event.id)
            .outerjoin(DocAnchor, DocAnchor.doc_id == EventDoc.doc_id)
            .order_by(Event.score_plantao.desc(), Event.created_at.desc())
        )
        if status:
            stmt = stmt.where(Event.status == status)
        if lane:
            stmt = stmt.where(Event.lane == lane)
            
        stmt = stmt.limit(limit * 5) # Oversampling because of joins
        result = await session.execute(stmt)
        rows = result.all()
        
        events_dict = {}
        for event, anchor in rows:
            if event.id not in events_dict:
                events_dict[event.id] = {
                    "id": event.id,
                    "status": event.status,
                    "summary": event.summary,
                    "score": event.score_plantao,
                    "lane": event.lane,
                    "created_at": event.created_at,
                    "anchors": []
                }
            if anchor:
                events_dict[event.id]["anchors"].append({
                    "type": anchor.anchor_type,
                    "value": anchor.anchor_value
                })
        
        return sorted(events_dict.values(), key=lambda x: x["score"], reverse=True)[:limit]


# ─── Dashboard ───
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard():
    """Painel de Controle Radar de Pautas."""
    async with async_session_factory() as session:
        sources_count = (await session.execute(select(func.count()).select_from(Source))).scalar() or 0
        events_hot = (await session.execute(select(func.count()).select_from(Event).where(Event.status == EventStatus.HOT))).scalar() or 0
        events_new = (await session.execute(select(func.count()).select_from(Event).where(Event.status == EventStatus.NEW))).scalar() or 0
        docs_count = (await session.execute(select(func.count()).select_from(Document))).scalar() or 0
        
        # Fetch top events for the feed with anchors
        stmt = (
            select(Event, DocAnchor)
            .outerjoin(EventDoc, EventDoc.event_id == Event.id)
            .outerjoin(DocAnchor, DocAnchor.doc_id == EventDoc.doc_id)
            .where(Event.status != EventStatus.IGNORED)
            .order_by(Event.score_plantao.desc(), Event.created_at.desc())
            .limit(60) # Joins can duplicate events
        )
        result = await session.execute(stmt)
        rows = result.all()
        
        events_dict = {}
        for event, anchor in rows:
            if event.id not in events_dict:
                events_dict[event.id] = {
                    "id": event.id,
                    "status": event.status,
                    "summary": event.summary,
                    "lane": event.lane,
                    "score": event.score_plantao,
                    "created_at": event.created_at,
                    "anchors": []
                }
            if anchor:
                events_dict[event.id]["anchors"].append(anchor)

    events_html = ""
    for eid, e in list(events_dict.items())[:12]:
        lane_class = f"lane-{e['lane']}" if e['lane'] else "lane-geral"
        p_class = "hot" if e['status'] == EventStatus.HOT else ""
        
        anchors_html = ""
        unique_anchors = { (a.anchor_type, a.anchor_value) for a in e['anchors'] }
        for atype, aval in list(unique_anchors)[:3]:
            anchors_html += f'<span class="anchor-tag">{atype}: {aval[:15]}</span>'

        events_html += f'''
        <div class="event-card {p_class}">
            <div class="event-header">
                <span class="lane-tag {lane_class}">{e['lane'] or 'geral'}</span>
                <span class="score-tag">{int(e['score'])}%</span>
            </div>
            <div class="event-summary">{e['summary'] or 'Sem resumo'}</div>
            <div class="anchor-list">
                {anchors_html}
            </div>
            <div class="event-meta">ID: #{e['id']} | {e['status']} | {e['created_at'].strftime('%H:%M')}</div>
        </div>
        '''

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
                --hot: #ef4444;
                --warning: #fca311;
            }}
            * {{ margin: 0; padding: 0; box-sizing: border-box; }}
            body {{
                font-family: 'Outfit', sans-serif;
                background: var(--bg);
                color: var(--text);
                min-height: 100vh;
                background-image: radial-gradient(circle at 50% 50%, #1e293b 0%, #0f172a 100%);
                padding-bottom: 50px;
            }}
            .container {{ max-width: 1100px; margin: 0 auto; padding: 40px 20px; }}
            header {{ margin-bottom: 50px; text-align: center; }}
            h1 {{ font-size: 2.5rem; font-weight: 700; margin-bottom: 10px; color: var(--accent); letter-spacing: -1px; }}
            .pulse {{
                display: inline-flex;
                align-items: center;
                font-size: 0.8rem;
                color: var(--success);
                font-weight: 600;
                background: rgba(34, 197, 94, 0.1);
                padding: 4px 12px;
                border-radius: 20px;
            }}
            .pulse-dot {{
                width: 8px; height: 8px; background: var(--success);
                border-radius: 50%; margin-right: 8px;
                animation: pulse 2s infinite;
            }}
            @keyframes pulse {{
                0% {{ box-shadow: 0 0 0 0 rgba(34, 197, 94, 0.7); }}
                70% {{ box-shadow: 0 0 0 8px rgba(34, 197, 94, 0); }}
                100% {{ box-shadow: 0 0 0 0 rgba(34, 197, 94, 0); }}
            }}
            .stats-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
                gap: 20px;
                margin-bottom: 50px;
            }}
            .stat-card {{
                background: var(--card);
                border: 1px solid rgba(255, 255, 255, 0.05);
                padding: 20px;
                border-radius: 16px;
                text-align: center;
                backdrop-filter: blur(5px);
            }}
            .stat-card .val {{ font-size: 2.2rem; font-weight: 700; display: block; }}
            .stat-card .lab {{ color: var(--subtext); text-transform: uppercase; font-size: 0.65rem; letter-spacing: 1.5px; margin-top: 4px; }}
            
            .feed-section {{ margin-top: 40px; }}
            .section-title {{ font-size: 1.4rem; font-weight: 600; margin-bottom: 25px; color: var(--text); display: flex; align-items: center; }}
            .section-title::after {{ content: ''; height: 1px; flex: 1; background: rgba(255,255,255,0.1); margin-left: 20px; }}
            
            .feed-grid {{
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
                gap: 20px;
            }}
            .event-card {{
                background: var(--card);
                border: 1px solid rgba(255, 255, 255, 0.05);
                border-radius: 16px;
                padding: 24px;
                transition: all 0.3s ease;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                min-height: 220px;
            }}
            .event-card:hover {{ transform: translateY(-4px); border-color: var(--accent); background: rgba(30, 41, 59, 0.9); }}
            .event-card.hot {{ border-left: 4px solid var(--hot); }}
            
            .event-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }}
            .lane-tag {{
                font-size: 0.7rem;
                font-weight: 700;
                text-transform: uppercase;
                padding: 2px 8px;
                border-radius: 4px;
                background: rgba(255,255,255,0.1);
            }}
            .lane-politica {{ background: rgba(56, 189, 248, 0.2); color: #38bdf8; }}
            .lane-justica {{ background: rgba(167, 139, 250, 0.2); color: #a78bfa; }}
            .lane-economia {{ background: rgba(34, 197, 94, 0.2); color: #22c55e; }}
            
            .score-tag {{ font-weight: 700; font-size: 0.9rem; color: var(--accent); }}
            .event-summary {{ font-size: 1.1rem; line-height: 1.4; font-weight: 400; margin-bottom: 15px; }}
            
            .anchor-list {{ display: flex; flex-wrap: wrap; gap: 6px; margin-bottom: 15px; }}
            .anchor-tag {{
                font-size: 0.6rem;
                background: rgba(255, 255, 255, 0.05);
                padding: 2px 6px;
                border-radius: 4px;
                color: var(--subtext);
                border: 1px solid rgba(255,255,255,0.1);
                white-space: nowrap;
            }}

            .event-meta {{ font-size: 0.7rem; color: var(--subtext); border-top: 1px solid rgba(255,255,255,0.05); padding-top: 10px; }}
            
            .footer-links {{ margin-top: 60px; display: flex; justify-content: center; gap: 15px; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 30px; }}
            .btn {{
                padding: 10px 20px;
                border-radius: 10px;
                text-decoration: none;
                color: var(--subtext);
                font-weight: 600;
                font-size: 0.8rem;
                background: rgba(255, 255, 255, 0.03);
                border: 1px solid rgba(255, 255, 255, 0.05);
                transition: all 0.2s ease;
            }}
            .btn:hover {{ background: var(--accent); color: var(--bg); }}
        </style>
    </head>
    <body>
        <div class="container">
            <header>
                <h1>Radar de Pautas</h1>
                <div class="pulse">
                    <div class="pulse-dot"></div>
                    SITUAÇÃO DA SALA DE IMPRENSA: ESTÁVEL
                </div>
            </header>

            <div class="stats-grid">
                <div class="stat-card">
                    <span class="val">{sources_count}</span>
                    <span class="lab">Fontes</span>
                </div>
                <div class="stat-card">
                    <span class="val" style="color: var(--warning);">{events_new}</span>
                    <span class="lab">Sinais Novos</span>
                </div>
                <div class="stat-card">
                    <span class="val" style="color: var(--hot);">{events_hot}</span>
                    <span class="lab">Pautas Quentes (HOT)</span>
                </div>
                <div class="stat-card">
                    <span class="val">{docs_count}</span>
                    <span class="lab">Docs Totais</span>
                </div>
            </div>

            <section class="feed-section">
                <h2 class="section-title">Feed de Inteligência Editorial</h2>
                <div class="feed-grid">
                    {events_html}
                </div>
            </section>

            <div class="footer-links">
                <a href="/docs" class="btn">API Docs</a>
                <a href="/health" class="btn">Health</a>
                <a href="/metrics" class="btn">Metrics</a>
                <a href="/api/events" class="btn">JSON DATA</a>
            </div>
        </div>
    </body>
    </html>
    """


# ── Health ──
@app.get("/health", tags=["ops"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "service": "radar-de-pautas"}


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
