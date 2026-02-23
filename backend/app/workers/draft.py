"""Smart Drafting Worker — Blueprint §14.

Uses LLM (Gemini) to generate concise factual summaries, 
sentiment analysis, and editorial tone suggestions.
"""
from __future__ import annotations

import asyncio
import logging
import json
from datetime import datetime
from sqlalchemy import select

from app.celery_app import celery
from app.db import async_session_factory
from app.models.event import Event, EventDoc
from app.models.document import Document
from app.config import settings

logger = logging.getLogger(__name__)

# Initialize Gemini if key is available
GENAI_AVAILABLE = False
try:
    if settings.GEMINI_API_KEY:
        import google.generativeai as genai
        genai.configure(api_key=settings.GEMINI_API_KEY)
        GENAI_AVAILABLE = True
        logger.info("Gemini SDK configured successfully.")
    else:
        logger.warning("GEMINI_API_KEY not found. Drafting will run in MOCK mode.")
except ImportError:
    logger.error("google-generativeai SDK not found.")

@celery.task(name="app.workers.draft.run_drafting")
def run_drafting(event_id: int):
    """Orchestrate LLM analysis for a canonical event."""
    asyncio.run(_async_run_drafting(event_id))

async def _async_run_drafting(event_id: int):
    async with async_session_factory() as session:
        # 1. Fetch Event and its Documents
        stmt = (
            select(Document)
            .join(EventDoc, EventDoc.doc_id == Document.id)
            .where(EventDoc.event_id == event_id)
        )
        result = await session.execute(stmt)
        docs = result.scalars().all()
        
        if not docs:
            logger.warning(f"No documents found for event {event_id}. Skipping draft.")
            return

        # Prepare context (Title + first 3000 chars of each doc)
        context = ""
        for i, doc in enumerate(docs[:5]): # Max 5 docs for context
            context += f"--- Document {i+1} ({doc.title}) ---\n"
            context += (doc.clean_text or "")[:3000] + "\n\n"

        # 2. LLM Call or Mock
        if GENAI_AVAILABLE:
            try:
                model = genai.GenerativeModel(settings.LLM_MODEL)
                prompt = f"""
                Analise os documentos abaixo sobre um evento de 'hard news' no Brasil.
                Gere um JSON com os seguintes campos:
                - 'summary': Um resumo factual de 2 parágrafos.
                - 'bullet_points': Lista de 3 a 5 fatos principais.
                - 'tone': O tom editorial (ex: 'urgente', 'informativo', 'crítico').
                - 'sentiment_score': Um float de -1.0 (muito negativo) a 1.0 (muito positivo).
                - 'editor_note': Sugestão para o jornalista sobre o que falta investigar.

                DOCUMENTOS:
                {context}
                
                Responda APENAS o JSON.
                """
                response = await asyncio.to_thread(model.generate_content, prompt)
                raw_text = response.text.replace("```json", "").replace("```", "").strip()
                draft_data = json.loads(raw_text)
                logger.info(f"Draft generated via Gemini for event {event_id}")
            except Exception as e:
                logger.error(f"Gemini API call failed: {e}")
                return
        else:
            # Mock Data for testing/backend architecture validation
            draft_data = {
                "summary": "Resumo gerado em modo MOCK. (Aguardando Chave de API)",
                "bullet_points": ["Fato 1 extraído", "Fato 2 detectado"],
                "tone": "informativo",
                "sentiment_score": 0.0,
                "editor_note": "Confirme a chave de API em app/config.py para habilitar NLP real."
            }

        # 3. Persistence
        stmt = select(Event).where(Event.id == event_id)
        result = await session.execute(stmt)
        event = result.scalar()
        
        if event:
            event.draft_json = draft_data
            event.sentiment_score = draft_data.get("sentiment_score", 0.0)
            # Update event summary if draft summary exists
            if draft_data.get("summary"):
                event.summary = draft_data["summary"]
            
            await session.commit()
            logger.info(f"Event {event_id} updated with new draft.")
