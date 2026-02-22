"""Source model — Blueprint §6 / §8."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Source(Base):
    """Fonte jornalística configurada via Source Profile DSL (§6)."""

    __tablename__ = "sources"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    domain: Mapped[str] = mapped_column(String(512), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False, comment="1..3")
    is_official: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    lang: Mapped[str] = mapped_column(String(8), default="pt-BR", nullable=False)
    fetch_policy_json: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment="Full Source Profile DSL — pool, strategy, endpoints, limits, etc.",
    )
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
        return f"<Source id={self.id} domain={self.domain!r} tier={self.tier}>"
