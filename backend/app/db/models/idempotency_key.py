"""idempotency_keys — API_SPEC.md §8 cache for `Idempotency-Key` on `POST /api/v1/documents`.
Migration 0009_idempotency_keys. T-12.2 (Phase 12 reconciliation).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

_TZ = DateTime(timezone=True)


class IdempotencyKey(Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (
        CheckConstraint(
            "status IN ('in_progress', 'completed')", name="ck_idempotency_status"
        ),
        CheckConstraint(
            "(status = 'completed' AND response_status_code IS NOT NULL "
            "AND response_body IS NOT NULL) "
            "OR (status = 'in_progress' AND response_status_code IS NULL "
            "AND response_body IS NULL)",
            name="ck_idempotency_completed_shape",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    idempotency_key: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    request_body_hash: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(Text)
    response_status_code: Mapped[int | None] = mapped_column(Integer, default=None)
    response_body: Mapped[dict[str, object] | None] = mapped_column(JSONB, default=None)
    created_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(_TZ, default=lambda: datetime.now(UTC))
    expires_at: Mapped[datetime] = mapped_column(_TZ)
