"""answers — immutable record of one question and the decision made. DATABASE.md §3.5,
DOMAIN_MODEL.md §4.5."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ARRAY, DateTime, ForeignKey, Integer, Numeric, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.answer_citation import AnswerCitation
    from app.db.models.user import User

_TZ = DateTime(timezone=True)
_SCORE = Numeric(6, 4)


class Answer(Base):
    __tablename__ = "answers"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    asked_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    # RET-003: nullable from day one, not deferred — redaction must not be a breaking API change.
    question: Mapped[str | None] = mapped_column(Text, default=None)
    question_hash: Mapped[str] = mapped_column(Text)
    question_redacted_at: Mapped[datetime | None] = mapped_column(_TZ, default=None)
    status: Mapped[str] = mapped_column(Text)
    answer_text: Mapped[str | None] = mapped_column(Text, default=None)
    confidence: Mapped[Decimal] = mapped_column(_SCORE)
    threshold: Mapped[Decimal] = mapped_column(_SCORE)
    top_similarity: Mapped[Decimal | None] = mapped_column(_SCORE, default=None)
    retrieved_chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    context_token_count: Mapped[int] = mapped_column(Integer, default=0)
    document_filter: Mapped[list[uuid.UUID] | None] = mapped_column(
        ARRAY(UUID(as_uuid=True)), default=None
    )
    embedding_model: Mapped[str] = mapped_column(Text)
    llm_model: Mapped[str | None] = mapped_column(Text, default=None)
    prompt_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    completion_tokens: Mapped[int | None] = mapped_column(Integer, default=None)
    latency_ms: Mapped[int] = mapped_column(Integer)
    refusal_code: Mapped[str | None] = mapped_column(Text, default=None)
    confidence_report: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    retrieval_trace: Mapped[list[object]] = mapped_column(JSONB, default=list)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))

    asked_by_user: Mapped["User"] = relationship(back_populates="answers")
    citations: Mapped[list["AnswerCitation"]] = relationship(back_populates="answer")
