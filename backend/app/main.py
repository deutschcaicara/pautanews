"""FastAPI application — health, metrics, CORS, SSE and product APIs."""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    generate_latest,
    multiprocess,
)
from starlette.responses import PlainTextResponse, Response, HTMLResponse, StreamingResponse
from sqlalchemy import select, func, desc, and_, or_
from app.db import async_session_factory
from app.models.source import Source
from app.models.event import Event, EventStatus, EventDoc, EventState
from app.models.document import Document
from app.models.anchor import DocAnchor
from app.models.entity_mention import EntityMention
from app.models.merge import MergeAudit
from app.models.feedback import FeedbackEvent
from app.models.score import EventScore
from app.deltas import generate_full_delta

from app.config import settings
from app.logging_config import setup_logging
from app.metrics import SSE_EVENTS_SENT_TOTAL
from app.observability import setup_opentelemetry

logger = logging.getLogger(__name__)


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _sse_frame(event_type: str, payload: dict) -> str:
    return f"event: {event_type}\ndata: {_json_dumps(payload)}\n\n"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan — setup / teardown."""
    setup_logging()
    setup_opentelemetry(app)
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
from app.api.cms import router as cms_router
from app.api.ui import router as ui_router

app.include_router(feedback_router)
app.include_router(cms_router)
app.include_router(ui_router)

# ── API ──
@app.get("/api/events", tags=["content"])
async def get_events(status: str | None = None, lane: str | None = None, limit: int = 20):
    """Retorna feed de eventos com âncoras e scores."""
    async with async_session_factory() as session:
        stmt = (
            select(Event, EventDoc, DocAnchor, EventScore)
            .outerjoin(EventDoc, EventDoc.event_id == Event.id)
            .outerjoin(DocAnchor, DocAnchor.doc_id == EventDoc.doc_id)
            .outerjoin(EventScore, EventScore.event_id == Event.id)
            .where(Event.canonical_event_id.is_(None))
            .order_by(Event.score_plantao.desc(), Event.created_at.desc())
        )
        if status:
            stmt = stmt.where(Event.status == status)
        else:
            stmt = stmt.where(Event.status.notin_([EventStatus.IGNORED, EventStatus.EXPIRED]))
        if lane:
            stmt = stmt.where(Event.lane == lane)
            
        stmt = stmt.limit(limit * 5) # Oversampling because of joins
        result = await session.execute(stmt)
        rows = result.all()
        
        events_dict = {}
        for event, event_doc, anchor, score_row in rows:
            if event.id not in events_dict:
                events_dict[event.id] = {
                    "id": event.id,
                    "status": event.status,
                    "summary": event.summary,
                    "score": event.score_plantao,
                    "score_oceano_azul": (score_row.score_oceano_azul if score_row else None),
                    "lane": event.lane,
                    "created_at": event.created_at,
                    "last_seen_at": event.last_seen_at,
                    "flags_json": event.flags_json,
                    "anchors": [],
                    "_anchors_seen": set(),
                    "_doc_ids": set(),
                    "_source_ids": set(),
                    "reasons_json": (score_row.reasons_json if score_row else None),
                }
            if event_doc:
                events_dict[event.id]["_doc_ids"].add(int(event_doc.doc_id))
                events_dict[event.id]["_source_ids"].add(int(event_doc.source_id))
            if anchor:
                key = (str(anchor.anchor_type), str(anchor.anchor_value))
                if key not in events_dict[event.id]["_anchors_seen"]:
                    events_dict[event.id]["_anchors_seen"].add(key)
                    events_dict[event.id]["anchors"].append({
                        "type": anchor.anchor_type,
                        "value": anchor.anchor_value
                    })

        payload = []
        for row in events_dict.values():
            row.pop("_anchors_seen", None)
            row["doc_count"] = len(row.pop("_doc_ids", []))
            row["source_count"] = len(row.pop("_source_ids", []))
            payload.append(row)
        return sorted(payload, key=lambda x: (x["score"] or 0.0), reverse=True)[:limit]


@app.get("/api/plantao", tags=["content"])
async def get_plantao(status: str | None = None, lane: str | None = None, limit: int = 20):
    """Alias MVP para feed Plantão."""
    return await get_events(status=status, lane=lane, limit=limit)


@app.get("/api/events/{event_id}", tags=["content"])
async def get_event_detail(event_id: int):
    """Event detail (timeline/docs/anchors/scores) with basic tombstone support."""
    async with async_session_factory() as session:
        event = (await session.execute(select(Event).where(Event.id == event_id))).scalar()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")

        if event.canonical_event_id:
            canonical = (
                await session.execute(select(Event).where(Event.id == event.canonical_event_id))
            ).scalar()
            return {
                "id": event.id,
                "status": event.status,
                "tombstone": True,
                "canonical_event_id": event.canonical_event_id,
                "redirect_hint": f"/evento/{event.canonical_event_id}",
                "canonical_event": (
                    {
                        "id": canonical.id,
                        "status": canonical.status,
                        "summary": canonical.summary,
                        "lane": canonical.lane,
                        "score_plantao": canonical.score_plantao,
                    }
                    if canonical
                    else None
                ),
            }

        score_row = (await session.execute(select(EventScore).where(EventScore.event_id == event_id))).scalar()

        doc_rows = (
            await session.execute(
                select(Document, EventDoc)
                .join(EventDoc, EventDoc.doc_id == Document.id)
                .where(EventDoc.event_id == event_id)
                .order_by(EventDoc.seen_at.desc())
            )
        ).all()

        anchor_rows = (
            await session.execute(
                select(DocAnchor)
                .join(EventDoc, EventDoc.doc_id == DocAnchor.doc_id)
                .where(EventDoc.event_id == event_id)
            )
        ).scalars().all()

        entity_rows = (
            await session.execute(
                select(EntityMention)
                .join(EventDoc, EventDoc.doc_id == EntityMention.doc_id)
                .where(EventDoc.event_id == event_id)
            )
        ).scalars().all()

        deltas = None
        if len(doc_rows) >= 2:
            latest_doc_id = doc_rows[0][0].id
            prev_doc_id = doc_rows[1][0].id
            anchors_by_doc: dict[int, list[str]] = {latest_doc_id: [], prev_doc_id: []}
            values_by_doc: dict[int, float | None] = {latest_doc_id: None, prev_doc_id: None}
            entities_by_doc: dict[int, list[str]] = {latest_doc_id: [], prev_doc_id: []}

            for a in anchor_rows:
                if a.doc_id in anchors_by_doc:
                    anchors_by_doc[a.doc_id].append(f"{a.anchor_type}:{a.anchor_value}")
                    if a.anchor_type == "VALOR" and str(a.anchor_value).startswith("BRL:"):
                        try:
                            values_by_doc[a.doc_id] = float(str(a.anchor_value).split(":", 1)[1])
                        except Exception:
                            pass
            for e in entity_rows:
                if e.doc_id in entities_by_doc:
                    entities_by_doc[e.doc_id].append(e.entity_key)

            deltas = generate_full_delta(
                {
                    "anchors": anchors_by_doc[prev_doc_id],
                    "value": values_by_doc[prev_doc_id],
                    "entities": entities_by_doc[prev_doc_id],
                    "time": None,
                },
                {
                    "anchors": anchors_by_doc[latest_doc_id],
                    "value": values_by_doc[latest_doc_id],
                    "entities": entities_by_doc[latest_doc_id],
                    "time": None,
                },
            )

        return {
            "event": {
                "id": event.id,
                "status": event.status,
                "summary": event.summary,
                "lane": event.lane,
                "flags_json": event.flags_json,
                "first_seen_at": event.first_seen_at,
                "last_seen_at": event.last_seen_at,
                "score_plantao": event.score_plantao,
            },
            "scores": {
                "score_plantao": (score_row.score_plantao if score_row else None),
                "score_oceano_azul": (score_row.score_oceano_azul if score_row else None),
                "reasons_json": (score_row.reasons_json if score_row else None),
            },
            "docs": [
                {
                    "doc_id": doc.id,
                    "url": doc.url,
                    "canonical_url": doc.canonical_url,
                    "title": doc.title,
                    "author": doc.author,
                    "published_at": doc.published_at,
                    "modified_at": doc.modified_at,
                    "lang": doc.lang,
                    "snapshot_id": doc.snapshot_id,
                    "version_no": doc.version_no,
                    "seen_at": rel.seen_at,
                    "is_primary": rel.is_primary,
                }
                for doc, rel in doc_rows
            ],
            "anchors": [
                {
                    "type": a.anchor_type,
                    "value": a.anchor_value,
                    "doc_id": a.doc_id,
                }
                for a in anchor_rows
            ],
            "entity_mentions": [
                {
                    "doc_id": e.doc_id,
                    "entity_key": e.entity_key,
                    "label": e.label,
                    "confidence": e.confidence,
                }
                for e in entity_rows
            ],
            "deltas": deltas,
        }


@app.get("/api/events/{event_id}/state-history", tags=["content"])
async def get_event_state_history(event_id: int, limit: int = 100):
    """State transition history for an event."""
    async with async_session_factory() as session:
        event = (await session.execute(select(Event).where(Event.id == event_id))).scalar()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        rows = (
            await session.execute(
                select(EventState)
                .where(EventState.event_id == event_id)
                .order_by(EventState.updated_at.desc(), EventState.id.desc())
                .limit(max(1, min(limit, 500)))
            )
        ).scalars().all()
        return {
            "event_id": event_id,
            "items": [
                {
                    "id": row.id,
                    "status": row.status,
                    "status_reason": row.status_reason,
                    "updated_at": row.updated_at,
                }
                for row in rows
            ],
        }


@app.get("/api/events/{event_id}/merge-audit", tags=["content"])
async def get_event_merge_audit(event_id: int, limit: int = 100):
    """Merge audit rows where event appears as source or target."""
    async with async_session_factory() as session:
        event = (await session.execute(select(Event).where(Event.id == event_id))).scalar()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        rows = (
            await session.execute(
                select(MergeAudit)
                .where(
                    (MergeAudit.from_event_id == event_id) | (MergeAudit.to_event_id == event_id)
                )
                .order_by(MergeAudit.created_at.desc(), MergeAudit.id.desc())
                .limit(max(1, min(limit, 500)))
            )
        ).scalars().all()
        return {
            "event_id": event_id,
            "items": [
                {
                    "id": row.id,
                    "from_event_id": row.from_event_id,
                    "to_event_id": row.to_event_id,
                    "reason_code": row.reason_code,
                    "evidence_json": row.evidence_json,
                    "created_at": row.created_at,
                }
                for row in rows
            ],
        }


@app.get("/api/events/{event_id}/feedback", tags=["content"])
async def get_event_feedback(event_id: int, limit: int = 100):
    """Editorial feedback history for an event (for backtest inspection)."""
    async with async_session_factory() as session:
        event = (await session.execute(select(Event).where(Event.id == event_id))).scalar()
        if not event:
            raise HTTPException(status_code=404, detail="Event not found")
        rows = (
            await session.execute(
                select(FeedbackEvent)
                .where(FeedbackEvent.event_id == event_id)
                .order_by(FeedbackEvent.created_at.desc(), FeedbackEvent.id.desc())
                .limit(max(1, min(limit, 500)))
            )
        ).scalars().all()
        return {
            "event_id": event_id,
            "items": [
                {
                    "id": row.id,
                    "action": row.action,
                    "actor": row.actor,
                    "payload_json": row.payload_json,
                    "created_at": row.created_at,
                }
                for row in rows
            ],
        }


@app.get("/api/oceano-azul", tags=["content"])
async def get_oceano_azul(limit: int = 20, min_score: float = 0.0):
    """Oceano Azul ranking by SCORE_OCEANO_AZUL."""
    async with async_session_factory() as session:
        rows = (
            await session.execute(
                select(Event, EventScore)
                .join(EventScore, EventScore.event_id == Event.id)
                .where(
                    Event.canonical_event_id.is_(None),
                    EventScore.score_oceano_azul >= min_score,
                    Event.status.notin_([EventStatus.IGNORED, EventStatus.EXPIRED]),
                )
                .order_by(EventScore.score_oceano_azul.desc(), Event.updated_at.desc())
                .limit(limit)
            )
        ).all()

        return [
            {
                "id": event.id,
                "status": event.status,
                "summary": event.summary,
                "lane": event.lane,
                "score_oceano_azul": score.score_oceano_azul,
                "score_plantao": score.score_plantao,
                "reasons_json": score.reasons_json,
                "flags_json": event.flags_json,
                "updated_at": event.updated_at,
            }
            for event, score in rows
        ]


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
            .where(
                Event.canonical_event_id.is_(None),
                Event.status.notin_([EventStatus.IGNORED, EventStatus.EXPIRED]),
            )
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


@app.get("/events/stream", tags=["sse"])
async def sse_stream(request: Request) -> StreamingResponse:
    """SSE endpoint (DB-polling MVP) emitting upserts, state changes and merges."""

    async def event_generator() -> AsyncGenerator[str, None]:
        last_event_cursor_ts = None
        last_event_cursor_id = 0
        last_state_cursor_ts = None
        last_state_cursor_id = 0
        last_merge_cursor_ts = None
        last_merge_cursor_id = 0

        while True:
            if await request.is_disconnected():
                break

            emitted = False
            async with async_session_factory() as session:
                event_stmt = (
                    select(Event, EventScore)
                    .outerjoin(EventScore, EventScore.event_id == Event.id)
                    .where(Event.canonical_event_id.is_(None))
                    .order_by(Event.updated_at.asc(), Event.id.asc())
                    .limit(100)
                )
                if last_event_cursor_ts is not None:
                    event_stmt = event_stmt.where(
                        or_(
                            Event.updated_at > last_event_cursor_ts,
                            and_(
                                Event.updated_at == last_event_cursor_ts,
                                Event.id > last_event_cursor_id,
                            ),
                        )
                    )
                event_rows = (await session.execute(event_stmt)).all()
                for event, score in event_rows:
                    emitted = True
                    SSE_EVENTS_SENT_TOTAL.labels(event_type="EVENT_UPSERT").inc()
                    yield _sse_frame(
                        "EVENT_UPSERT",
                        {
                            "id": event.id,
                            "status": event.status,
                            "summary": event.summary,
                            "lane": event.lane,
                            "flags_json": event.flags_json,
                            "updated_at": event.updated_at,
                            "score_plantao": (score.score_plantao if score else event.score_plantao),
                            "score_oceano_azul": (score.score_oceano_azul if score else None),
                            "reasons_json": (score.reasons_json if score else None),
                        },
                    )
                    last_event_cursor_ts = event.updated_at
                    last_event_cursor_id = int(event.id)

                state_stmt = select(EventState).order_by(EventState.updated_at.asc(), EventState.id.asc()).limit(100)
                if last_state_cursor_ts is not None:
                    state_stmt = state_stmt.where(
                        or_(
                            EventState.updated_at > last_state_cursor_ts,
                            and_(
                                EventState.updated_at == last_state_cursor_ts,
                                EventState.id > last_state_cursor_id,
                            ),
                        )
                    )
                state_rows = (await session.execute(state_stmt)).scalars().all()
                for row in state_rows:
                    emitted = True
                    SSE_EVENTS_SENT_TOTAL.labels(event_type="EVENT_STATE_CHANGED").inc()
                    yield _sse_frame(
                        "EVENT_STATE_CHANGED",
                        {
                            "event_id": row.event_id,
                            "status": row.status,
                            "status_reason": row.status_reason,
                            "updated_at": row.updated_at,
                        },
                    )
                    last_state_cursor_ts = row.updated_at
                    last_state_cursor_id = int(row.id)

                merge_stmt = select(MergeAudit).order_by(MergeAudit.created_at.asc(), MergeAudit.id.asc()).limit(100)
                if last_merge_cursor_ts is not None:
                    merge_stmt = merge_stmt.where(
                        or_(
                            MergeAudit.created_at > last_merge_cursor_ts,
                            and_(
                                MergeAudit.created_at == last_merge_cursor_ts,
                                MergeAudit.id > last_merge_cursor_id,
                            ),
                        )
                    )
                merge_rows = (await session.execute(merge_stmt)).scalars().all()
                for row in merge_rows:
                    emitted = True
                    SSE_EVENTS_SENT_TOTAL.labels(event_type="EVENT_MERGED").inc()
                    yield _sse_frame(
                        "EVENT_MERGED",
                        {
                            "from_event_id": row.from_event_id,
                            "to_event_id": row.to_event_id,
                            "reason_code": row.reason_code,
                            "evidence_json": row.evidence_json,
                            "created_at": row.created_at,
                        },
                    )
                    last_merge_cursor_ts = row.created_at
                    last_merge_cursor_id = int(row.id)

            if not emitted:
                SSE_EVENTS_SENT_TOTAL.labels(event_type="ping").inc()
                yield _sse_frame("ping", {})
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
