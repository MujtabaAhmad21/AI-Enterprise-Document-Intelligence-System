"""ingestion_jobs. DATABASE.md §3.4, DOMAIN_MODEL.md §4.4."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.document import Document

_TZ = DateTime(timezone=True)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("documents.id", ondelete="CASCADE")
    )
    generation: Mapped[int] = mapped_column(Integer)
    state: Mapped[str] = mapped_column(Text, default="queued")
    stage: Mapped[str | None] = mapped_column(Text, default=None)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    failure_code: Mapped[str | None] = mapped_column(Text, default=None)
    failure_message: Mapped[str | None] = mapped_column(Text, default=None)
    scheduled_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))
    started_at: Mapped[datetime | None] = mapped_column(_TZ, default=None)
    finished_at: Mapped[datetime | None] = mapped_column(_TZ, default=None)
    stage_timings: Mapped[dict[str, object]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))

    document: Mapped["Document"] = relationship(back_populates="ingestion_jobs")
