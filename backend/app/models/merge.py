"""MergeAudit model — Blueprint §8 / §11."""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class MergeAudit(Base):
    """Audit trail of event merges (TOMBSTONE process §11)."""

    __tablename__ = "merge_audit"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    from_event_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    to_event_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("events.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reason_code: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    def __repr__(self) -> str:
        return f"<MergeAudit id={self.id} {self.from_event_id} -> {self.to_event_id}>"
