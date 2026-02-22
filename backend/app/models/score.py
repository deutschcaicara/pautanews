"""EventScore model — Blueprint §8 / §12."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EventScore(Base):
    """Pontuações dual (Plantão / Oceano Azul) do evento."""

    __tablename__ = "event_scores"

    event_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("events.id", ondelete="CASCADE"),
        primary_key=True,
    )
    score_plantao: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    score_oceano_azul: Mapped[float] = mapped_column(Float, default=0.0, nullable=False, index=True)
    reasons_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="REASONS_CODES estáveis (§12.2)"
    )
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<EventScore event={self.event_id} P={self.score_plantao} OA={self.score_oceano_azul}>"
