"""DocAnchor + DocEvidenceFeature — Blueprint §8 / §10 Golden Regex output."""
from __future__ import annotations

from sqlalchemy import Float, ForeignKey, Integer, String, Boolean, Text, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DocAnchor(Base):
    """Âncora determinística extraída de um documento (CNPJ, CNJ, PL etc.)."""

    __tablename__ = "doc_anchors"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    doc_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    anchor_type: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        comment="CNPJ | CPF | CNJ | SEI | TCU | PL | ATO | VALOR | DATA | LINK_GOV | PDF",
    )
    anchor_value: Mapped[str] = mapped_column(String(512), nullable=False)
    evidence_ptr: Mapped[str | None] = mapped_column(
        Text, nullable=True, comment="Trecho original ou offset"
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)

    __table_args__ = (
        Index("ix_doc_anchors_type_value", "anchor_type", "anchor_value"),
    )

    def __repr__(self) -> str:
        return f"<DocAnchor id={self.id} type={self.anchor_type} value={self.anchor_value[:30]!r}>"


class DocEvidenceFeature(Base):
    """Feature vector de evidência por documento (Golden Regex summary)."""

    __tablename__ = "doc_evidence_features"

    doc_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("documents.id", ondelete="CASCADE"),
        primary_key=True,
    )
    evidence_score: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    has_pdf: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_official_domain: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    anchors_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    money_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    has_table_like: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    evidence_json: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, comment="Detailed evidence breakdown"
    )

    def __repr__(self) -> str:
        return f"<DocEvidenceFeature doc_id={self.doc_id} score={self.evidence_score}>"
