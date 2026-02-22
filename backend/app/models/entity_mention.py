"""EntityMention model — Blueprint §8."""
from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class EntityMention(Base):
    """Menção de entidade detectada no documento (NER / heurístico)."""

    __tablename__ = "entity_mentions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    entity_key: Mapped[str] = mapped_column(
        String(256), nullable=False, index=True, comment="Normalised key e.g. CPF or name slug"
    )
    label: Mapped[str] = mapped_column(
        String(64), nullable=False, comment="PER | ORG | LOC | GOV | EVENT"
    )
    span_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment='{"start": int, "end": int, "text": str}'
    )
    evidence_ptr: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    def __repr__(self) -> str:
        return f"<EntityMention id={self.id} key={self.entity_key!r} label={self.label}>"
