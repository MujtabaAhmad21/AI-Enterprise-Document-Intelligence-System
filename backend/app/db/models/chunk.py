"""document_chunks — the unit of retrieval and citation. DATABASE.md §3.3, DOMAIN_MODEL.md §4.3."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from pgvector.sqlalchemy import Vector
from sqlalchemy import Computed, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import TSVECTOR, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.config import settings
from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.document import Document

_TZ = DateTime(timezone=True)


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    generation: Mapped[int] = mapped_column(Integer)
    ordinal: Mapped[int] = mapped_column(Integer)
    content: Mapped[str] = mapped_column(Text)
    content_hash: Mapped[str] = mapped_column(Text)
    token_count: Mapped[int] = mapped_column(Integer)
    char_start: Mapped[int] = mapped_column(Integer)
    char_end: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer, default=None)
    page_end: Mapped[int | None] = mapped_column(Integer, default=None)
    section_path: Mapped[str | None] = mapped_column(Text, default=None)
    # DB-021/ADR-016: 1536 for text-embedding-3-small, rendered from EMBEDDING_DIM like the
    # migration that built the column (DB-014) — never hard-coded without the assertion.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.embedding_dim), default=None
    )
    embedding_model: Mapped[str | None] = mapped_column(Text, default=None)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, default=None)
    # DB-013: generated column. Computed() excludes it from INSERT/UPDATE — application code
    # MUST NOT write it; PostgreSQL maintains it.
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR, Computed("to_tsvector('english', content)", persisted=True)
    )
    created_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))

    document: Mapped["Document"] = relationship(back_populates="chunks")
