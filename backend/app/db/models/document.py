"""documents — aggregate root. DATABASE.md §3.2, DOMAIN_MODEL.md §4.2."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

_TZ = DateTime(timezone=True)

if TYPE_CHECKING:
    from app.db.models.chunk import DocumentChunk
    from app.db.models.ingestion_job import IngestionJob
    from app.db.models.user import User


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    uploaded_by: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="RESTRICT")
    )
    original_filename: Mapped[str] = mapped_column(Text)
    content_type: Mapped[str] = mapped_column(Text)
    byte_size: Mapped[int] = mapped_column(BigInteger)
    content_hash: Mapped[str] = mapped_column(Text)
    storage_key: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text, default="pending")
    generation: Mapped[int] = mapped_column(Integer, default=1)
    page_count: Mapped[int | None] = mapped_column(Integer, default=None)
    chunk_count: Mapped[int] = mapped_column(Integer, default=0)
    token_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_code: Mapped[str | None] = mapped_column(Text, default=None)
    failure_message: Mapped[str | None] = mapped_column(Text, default=None)
    uploaded_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))
    indexed_at: Mapped[datetime | None] = mapped_column(_TZ, default=None)
    deleted_at: Mapped[datetime | None] = mapped_column(_TZ, default=None)
    original_purged_at: Mapped[datetime | None] = mapped_column(_TZ, default=None)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))

    @property
    def original_purged(self) -> bool:
        """SC-024: derived for the wire (DocumentResponse.original_purged), not stored."""
        return self.original_purged_at is not None

    uploaded_by_user: Mapped["User"] = relationship(back_populates="documents")
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    ingestion_jobs: Mapped[list["IngestionJob"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
