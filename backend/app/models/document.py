"""Document model — Blueprint §8, versionado."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, func, Index
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Document(Base):
    """Documento normalizado extraído de um snapshot. Versionado por content_hash."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    url: Mapped[str] = mapped_column(String(2048), nullable=False, index=True)
    canonical_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    author: Mapped[str | None] = mapped_column(String(512), nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    modified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    clean_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    lang: Mapped[str | None] = mapped_column(String(8), nullable=True)
    content_hash: Mapped[str] = mapped_column(
        String(64), nullable=False, index=True, comment="SHA-256 of clean_text"
    )
    simhash: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True, index=True, comment="SimHash 64-bit for similarity"
    )
    version_no: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    snapshot_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("snapshots.id", ondelete="SET NULL"), nullable=True
    )
    source_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("sources.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    __table_args__ = (
        Index("ix_documents_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index("ix_documents_text_trgm", "clean_text", postgresql_using="gin", postgresql_ops={"clean_text": "gin_trgm_ops"}),
    )

    def __repr__(self) -> str:
        t = self.title[:50] if self.title else "N/A"
        return f"<Document id={self.id} title={t!r}>"
