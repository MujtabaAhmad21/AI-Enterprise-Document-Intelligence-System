"""answer_citations — the join that makes INV-001 a database constraint. DATABASE.md §3.6,
DOMAIN_MODEL.md §4.6."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.answer import Answer

_TZ = DateTime(timezone=True)


class AnswerCitation(Base):
    __tablename__ = "answer_citations"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    answer_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("answers.id", ondelete="CASCADE")
    )
    # DB-015: RESTRICT is load-bearing — cited evidence cannot vanish (INV-001).
    chunk_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("document_chunks.id", ondelete="RESTRICT")
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="RESTRICT")
    )
    marker: Mapped[int] = mapped_column(Integer)
    claim_index: Mapped[int] = mapped_column(Integer)
    quoted_span: Mapped[str | None] = mapped_column(Text, default=None)
    cosine_similarity: Mapped[Decimal] = mapped_column(Numeric(6, 4))
    rank: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))

    answer: Mapped["Answer"] = relationship(back_populates="citations")
