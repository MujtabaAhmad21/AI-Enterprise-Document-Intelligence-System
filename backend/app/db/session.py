"""Request-scoped async sessions. DB-038: expire_on_commit=False; services never commit — the
request/job dependency owns commit and rollback. No service opens a nested transaction.
"""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings
from app.errors import AppError

_statement_timeout_ms = settings.db_statement_timeout_seconds * 1000

engine = create_async_engine(
    settings.database_url.get_secret_value(),
    pool_size=settings.db_pool_size,
    max_overflow=settings.db_max_overflow,
    pool_timeout=settings.db_pool_timeout_seconds,
    echo=settings.db_echo,
    connect_args={"options": f"-c statement_timeout={_statement_timeout_ms}"},
)

async_session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def get_db() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding one session for the life of the request.

    An `AppError` is a deliberate, valid business outcome (401/404/409/...), not a failure
    requiring rollback: whatever was flushed on the way to raising it — most importantly an
    `audit_events` row such as `auth.login_failed` or `security.rejected_upload` (OBS-020) —
    is intentional and MUST survive. Only an unexpected exception rolls back, because at that
    point we no longer know what state is safe to keep.
    """
    async with async_session_factory() as session:
        try:
            yield session
        except AppError:
            await session.commit()
            raise
        except Exception:
            await session.rollback()
            raise
        else:
            await session.commit()
