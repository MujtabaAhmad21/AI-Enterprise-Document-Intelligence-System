"""users. DATABASE.md §3.1, DOMAIN_MODEL.md §4.1."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Text
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.db.models.answer import Answer
    from app.db.models.audit_event import AuditEvent
    from app.db.models.document import Document


class User(Base):
    __tablename__ = "users"

    # DB-002: UUID v4 generated application-side; the DB's gen_random_uuid() default is a
    # safety net only.
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(Text, default="member")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # DB-003: set explicitly by the application (datetime.now(UTC)), not the DB's now().
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC)
    )

    documents: Mapped[list["Document"]] = relationship(back_populates="uploaded_by_user")
    answers: Mapped[list["Answer"]] = relationship(back_populates="asked_by_user")
    audit_events: Mapped[list["AuditEvent"]] = relationship(back_populates="actor")
