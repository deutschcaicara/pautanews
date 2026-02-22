"""Snapshot model — Blueprint §8."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Snapshot(Base):
    """Raw page/response snapshot, immutable after creation."""

    __tablename__ = "snapshots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    fetched_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    headers_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    body_ref: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="S3 key or local path to raw body"
    )
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="SHA-256 of body"
    )
    snapshot_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, unique=True, comment="Dedup hash"
    )

    def __repr__(self) -> str:
        return f"<Snapshot id={self.id} url={self.url[:60]!r}>"
