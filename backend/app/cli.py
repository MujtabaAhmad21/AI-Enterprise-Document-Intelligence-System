"""Backend CLI entrypoints.

`export-openapi` (T-8.1, TYPESCRIPT_CONTRACT.md §3/TS-009): builds the app and prints its
OpenAPI document **without opening a database connection**: `FastAPI.openapi()` only
introspects routes/schemas already registered at import time, and the app's `lifespan` (which
runs the real readiness checks against Postgres, and now also starts the in-process ingestion
worker — T-11's DOP-001/DOP-002) is only invoked when something actually serves the app
(uvicorn, or a `TestClient` used as a context manager) — neither happens here. A valid
`Settings()` is still required (e.g. `DATABASE_URL` must be a well-formed URL string), since
`app.config` loads it eagerly at import time; it does not need to point at a reachable database.

`seed-users`/`seed-corpus` (T-11.7, MIGRATION_PLAN.md §6, MIG-030..033): dev/staging-only
seeding, deliberately a CLI command and never a migration (MIG-030) so production migrations
never create accounts. Each opens its own real database connection.
"""

import hashlib
import io
import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

# MIG-033: the fixture corpus lives at the repo root, outside the `backend/` build context
# (backend/Dockerfile copies only `app/`, `alembic.ini`, `migrations` — DOP-021 excludes
# `tests` from the image on purpose). Resolved two ways: running via `uv run` from `backend/`
# against a full clone (parents[2] of this file is the repo root), or the dev-only bind mount
# `docker-compose.yml` adds to the `api` service for exactly this command.
_FIXTURE_CANDIDATES = (
    Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "documents",
    Path("/app/tests/fixtures/documents"),
)
# Same three documents HANDOVER.md's dev environment has always seeded by hand, T-5.11's
# calibration sweep already exercises, and TEST-1003/1006 seed via e2e/_seed_lib.py.
_SEED_DOCUMENTS = ("acme_msa.pdf", "pump_manual.pdf", "hr_policy.docx")
_CONTENT_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}
_SEED_ADMIN_EMAIL = "admin@example.com"
_SEED_MEMBER_EMAIL = "member@example.com"


def export_openapi() -> None:
    from app.main import app

    json.dump(app.openapi(), sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")


def _fixtures_dir() -> Path:
    for candidate in _FIXTURE_CANDIDATES:
        if candidate.is_dir():
            return candidate
    raise SystemExit(
        "FATAL: fixture corpus not found (looked in "
        + ", ".join(str(c) for c in _FIXTURE_CANDIDATES)
        + "). seed-corpus needs tests/fixtures/documents — run via `uv run` from a full clone's "
        "backend/, or via `docker compose exec api ...` with the dev bind mount in place."
    )


def seed_users() -> None:
    """MIG-031/MIG-032: creates admin@example.com/member@example.com from
    SEED_ADMIN_PASSWORD/SEED_MEMBER_PASSWORD. Refuses in production and refuses if either
    password is unset — no fallback default password exists anywhere in this codebase."""
    import asyncio

    from app.config import settings

    if settings.is_production:
        print(
            "FATAL: seed-users refuses to run when ENVIRONMENT=production (MIG-031).",
            file=sys.stderr,
        )
        sys.exit(1)

    missing = [
        name
        for name, value in (
            ("SEED_ADMIN_PASSWORD", settings.seed_admin_password),
            ("SEED_MEMBER_PASSWORD", settings.seed_member_password),
        )
        if value is None
    ]
    if missing:
        print(
            "FATAL: seed-users refuses to run without " + ", ".join(missing) + " set "
            "(MIG-031: no fallback default password exists).",
            file=sys.stderr,
        )
        sys.exit(1)

    asyncio.run(_seed_users_async())


async def _seed_users_async() -> None:
    from sqlalchemy import select

    from app.auth.passwords import hash_password
    from app.config import settings
    from app.db.models import User
    from app.db.session import async_session_factory

    assert settings.seed_admin_password is not None
    assert settings.seed_member_password is not None
    accounts = (
        (_SEED_ADMIN_EMAIL, settings.seed_admin_password.get_secret_value(), "admin"),
        (_SEED_MEMBER_EMAIL, settings.seed_member_password.get_secret_value(), "member"),
    )

    async with async_session_factory() as session:
        for email, password, role in accounts:
            # MIG-032: idempotent — existing emails are skipped, not overwritten.
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing is not None:
                print(f"[seed-users] {email} already exists, skipping.")
                continue

            session.add(
                User(
                    id=uuid.uuid4(),
                    email=email,
                    password_hash=hash_password(password),
                    role=role,
                )
            )
            await session.commit()
            print(f"[seed-users] created {email} ({role})")


def seed_corpus() -> None:
    """MIG-033: dev only — loads the fixture corpus through the real ingestion pipeline (not
    hand-inserted chunk rows, which would have embeddings inconsistent with the pipeline's)."""
    import asyncio

    from app.config import settings

    if settings.is_production:
        print("FATAL: seed-corpus refuses to run when ENVIRONMENT=production.", file=sys.stderr)
        sys.exit(1)

    asyncio.run(_seed_corpus_async())


async def _seed_corpus_async() -> None:
    from sqlalchemy import select

    from app.db.models import Document, IngestionJob, User
    from app.db.session import async_session_factory
    from app.providers.factory import get_embedding_client
    from app.schemas.enums import DocumentStatus
    from app.services.ingestion_service import process_ingestion_job
    from app.storage.factory import get_storage

    fixtures_dir = _fixtures_dir()
    storage = get_storage()
    embedding_client = get_embedding_client()

    async with async_session_factory() as session:
        admin = (
            await session.execute(select(User).where(User.email == _SEED_ADMIN_EMAIL))
        ).scalar_one_or_none()
        if admin is None:
            print(
                f"FATAL: seed-corpus needs {_SEED_ADMIN_EMAIL} to already exist — "
                "run `seed-users` first (MIG-031).",
                file=sys.stderr,
            )
            sys.exit(1)

        for filename in _SEED_DOCUMENTS:
            content = (fixtures_dir / filename).read_bytes()
            content_hash = hashlib.sha256(content).hexdigest()

            # Idempotent by content hash (uq_documents_content_hash_live, migration 0002):
            # a rerun against an already-seeded database reuses the existing document.
            existing = (
                await session.execute(
                    select(Document).where(
                        Document.content_hash == content_hash, Document.deleted_at.is_(None)
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                print(f"[seed-corpus] {filename} already ingested ({existing.status}), skipping.")
                continue

            key = f"seed/{uuid.uuid4()}-{filename}"
            storage.put(key, io.BytesIO(content))

            now = datetime.now(UTC)
            document = Document(
                id=uuid.uuid4(),
                uploaded_by=admin.id,
                original_filename=filename,
                content_type=_CONTENT_TYPES[Path(filename).suffix],
                byte_size=len(content),
                content_hash=content_hash,
                storage_key=key,
                # Simulates the worker's claim (ING-033) — this script drives the pipeline
                # directly rather than enqueuing and waiting for a background loop to pick it up.
                status=DocumentStatus.EXTRACTING.value,
                generation=1,
                uploaded_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(document)
            await session.flush()

            job = IngestionJob(
                id=uuid.uuid4(),
                document_id=document.id,
                generation=1,
                state="running",
                max_attempts=3,
                scheduled_at=now,
                created_at=now,
                updated_at=now,
            )
            session.add(job)
            await session.flush()
            await session.commit()

            await process_ingestion_job(
                session, document, job, storage=storage, embedding_client=embedding_client
            )
            await session.refresh(document)
            print(f"[seed-corpus] {filename} -> {document.status} ({document.id})")
            if document.status != DocumentStatus.INDEXED.value:
                print(
                    f"[seed-corpus] WARNING: {filename} did not reach indexed "
                    f"(failure_code={document.failure_code!r} "
                    f"failure_message={document.failure_message!r})",
                    file=sys.stderr,
                )


_COMMANDS = {
    "export-openapi": export_openapi,
    "seed-users": seed_users,
    "seed-corpus": seed_corpus,
}


def main(argv: list[str] | None = None) -> None:
    args = argv if argv is not None else sys.argv[1:]
    if len(args) != 1 or args[0] not in _COMMANDS:
        print(f"usage: python -m app.cli {{{'|'.join(_COMMANDS)}}}", file=sys.stderr)
        sys.exit(2)
    _COMMANDS[args[0]]()


if __name__ == "__main__":
    main()
