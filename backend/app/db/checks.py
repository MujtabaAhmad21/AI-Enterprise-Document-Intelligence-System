"""Startup & readiness checks. DATABASE.md §6.

Run once at process start (exit non-zero on failure, FR-010) and on every GET /health/ready
call. Provider reachability is deliberately never included here (API-017).
"""

from dataclasses import dataclass
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class ReadinessResult:
    database: bool
    vector_extension: bool
    migrations_current: bool
    embedding_dimension: bool
    embedding_model_match: bool
    vector_index: bool
    migration_revision: str | None

    @property
    def ready(self) -> bool:
        return all(
            (
                self.database,
                self.vector_extension,
                self.migrations_current,
                self.embedding_dimension,
                self.embedding_model_match,
                self.vector_index,
            )
        )


def _code_head_revision() -> str | None:
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "migrations"))
    return ScriptDirectory.from_config(config).get_current_head()


async def _try_scalar(
    session: AsyncSession, sql: str, params: dict[str, object] | None = None
) -> object | None:
    """Runs one check in isolation. On failure (missing table/extension/relation — exactly
    what an unmigrated or mid-migration database looks like) rolls back so the aborted
    transaction doesn't poison the checks that run after it, and reports None rather than
    raising: a health endpoint must always answer, never 500."""
    try:
        result = await session.execute(text(sql), params or {})
        return result.scalar()
    except Exception:
        await session.rollback()
        return None


async def run_readiness_checks(session: AsyncSession) -> ReadinessResult:
    if await _try_scalar(session, "SELECT 1") is None:
        # DB reachable but returned no row is impossible for `SELECT 1`; treat as unreachable
        # exactly like the exception path below.
        return ReadinessResult(
            database=False,
            vector_extension=False,
            migrations_current=False,
            embedding_dimension=False,
            embedding_model_match=False,
            vector_index=False,
            migration_revision=None,
        )

    vector_extension = (
        await _try_scalar(session, "SELECT 1 FROM pg_extension WHERE extname = 'vector'")
    ) is not None

    db_revision = await _try_scalar(session, "SELECT version_num FROM alembic_version")
    migrations_current = db_revision is not None and db_revision == _code_head_revision()

    typmod = await _try_scalar(
        session,
        "SELECT atttypmod FROM pg_attribute "
        "WHERE attrelid = 'document_chunks'::regclass AND attname = 'embedding'",
    )
    # DB-014: pgvector's typmod IS the configured dimension (no offset, unlike e.g. varchar).
    embedding_dimension = typmod is not None and typmod == settings.embedding_dim

    # RAG-030/ENV-029/T-4.5: refuse readiness if any indexed chunk was embedded with a
    # different model than the one currently configured. No chunks yet -> vacuously true.
    model_mismatch_exists = await _try_scalar(
        session,
        "SELECT EXISTS ("
        "SELECT 1 FROM document_chunks WHERE embedding_model IS DISTINCT FROM :model"
        ")",
        {"model": settings.embedding_model},
    )
    embedding_model_match = model_mismatch_exists is False

    vector_index = (
        await _try_scalar(
            session, "SELECT 1 FROM pg_class WHERE relname = 'ix_chunks_embedding_hnsw'"
        )
    ) is not None

    return ReadinessResult(
        database=True,
        vector_extension=vector_extension,
        migrations_current=migrations_current,
        embedding_dimension=embedding_dimension,
        embedding_model_match=embedding_model_match,
        vector_index=vector_index,
        migration_revision=db_revision if isinstance(db_revision, str) else None,
    )
