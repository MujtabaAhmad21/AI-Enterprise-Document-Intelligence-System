"""SQLAlchemy 2.0 declarative base.

MIG-001: the schema is owned exclusively by Alembic migrations (migrations/versions/*.py).
Base.metadata.create_all() is never called anywhere, including tests — the real migration
chain runs instead, so the chain itself is continuously exercised (T-002, TEST-1002).
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
