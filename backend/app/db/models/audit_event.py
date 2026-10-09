"""audit_events — append-only operational history. DATABASE.md §3.7, DOMAIN_MODEL.md §4.7."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.user import User

_TZ = DateTime(timezone=True)


class AuditEvent(Base):
    """INV-029: never updated or deleted by application code (app/services/audit_service.py
    only ever inserts; the app's DB grants back this up — see migration 0008_grants)."""

    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), default=None
    )
    action: Mapped[str] = mapped_column(Text)
    target_type: Mapped[str] = mapped_column(Text)
    target_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    request_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), default=None)
    event_metadata: Mapped[dict[str, object]] = mapped_column(
        "metadata", JSONB, default=dict
    )
    created_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))

    actor: Mapped[Optional["User"]] = relationship(back_populates="audit_events")
