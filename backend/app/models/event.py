"""Event, EventDoc and EventState models — Blueprint §8."""
from __future__ import annotations

import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EventStatus(str, enum.Enum):
    """Enum de estados (fixo) — Blueprint §13.1."""

    NEW = "NEW"
    HYDRATING = "HYDRATING"
    PARTIAL_ENRICH = "PARTIAL_ENRICH"
    FAILED_ENRICH = "FAILED_ENRICH"
    QUARANTINE = "QUARANTINE"
    HOT = "HOT"
    MERGED = "MERGED"
    IGNORED = "IGNORED"
    EXPIRED = "EXPIRED"


class Event(Base):
    """Evento factual canônico. Pode agrupar múltiplos documentos."""

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    canonical_event_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("events.id"), nullable=True, comment="ID do evento que o absorveu (TOMBSTONE)"
    )
    status: Mapped[EventStatus] = mapped_column(
        String(32), default=EventStatus.NEW, nullable=False, index=True
    )
    flags_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="UNVERIFIED_VIRAL etc."
    )
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), index=True, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    def __repr__(self) -> str:
        return f"<Event id={self.id} status={self.status}>"


class EventDoc(Base):
    """Relacionamento muitos-para-muitos entre Eventos e Documentos."""

    __tablename__ = "event_docs"

    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), primary_key=True
    )
    doc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), primary_key=True
    )
    source_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("sources.id"), nullable=False, index=True
    )
    seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class EventState(Base):
    """Histórico de transições de estado de um evento."""

    __tablename__ = "event_state"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[EventStatus] = mapped_column(String(32), nullable=False)
    status_reason: Mapped[str | None] = mapped_column(String(256), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<EventState event={self.event_id} status={self.status}>"
