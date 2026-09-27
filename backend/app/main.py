"""ASGI application entrypoint. ARCHITECTURE.md §4."""

import asyncio
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api.handlers import register_exception_handlers
from app.api.router import api_v1_router
from app.api.routers.auth import router as auth_router
from app.api.routers.health import router as health_router
from app.api.routers.metrics import router as metrics_router
from app.config import settings
from app.db.checks import run_readiness_checks
from app.db.session import async_session_factory
from app.logging import configure_logging, get_logger
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.security import SecurityHeadersMiddleware
from app.providers.factory import get_embedding_client
from app.schemas.errors import ErrorResponse
from app.storage.factory import get_storage
from app.worker.loop import run_worker_loop
from app.worker.retention import run_retention_loop
from app.worker.retry import run_reclaim_loop

# DOP-002/DOP-030: shutdown gets a bounded grace period to let a poll loop finish its current
# iteration cleanly; past that, cancelling is safe (DOP-024 — nothing here holds a transaction
# across a sleep, and no in-flight ingestion job or answer is left partially persisted).
_SHUTDOWN_GRACE_SECONDS = 5.0

configure_logging(
    level=settings.log_level,
    service="api",
    version=settings.app_version,
    environment=settings.environment,
)
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # DATABASE.md §6: the same checks readiness runs per-request run once at process start;
    # on failure the process exits non-zero rather than serving traffic (FR-010).
    async with async_session_factory() as session:
        result = await run_readiness_checks(session)
    if not result.ready:
        logger.critical(
            "app.startup_readiness_failed",
            extra={
                "database": result.database,
                "vector_extension": result.vector_extension,
                "migrations_current": result.migrations_current,
                "embedding_dimension": result.embedding_dimension,
                "embedding_model_match": result.embedding_model_match,
                "vector_index": result.vector_index,
            },
        )
        sys.exit(1)
    logger.info("app.startup", extra={"environment": settings.environment})

    # DOP-001/DOP-002/DOP-030: in v1 the ingestion worker (job claiming + stuck-job reclaim)
    # and the retention sweep run inside this same process as background asyncio tasks —
    # ING-033's SELECT ... FOR UPDATE SKIP LOCKED claiming is already multi-process safe, which
    # is what lets a future APP_ROLE=worker split promote this to its own container with no
    # code change. An APP_ROLE=api process (that anticipated split) starts none of them.
    background_tasks: list[asyncio.Task[None]] = []
    stop_event = asyncio.Event()
    if settings.app_role != "api":
        storage = get_storage()
        embedding_client = get_embedding_client()
        background_tasks = [
            asyncio.create_task(
                run_worker_loop(
                    async_session_factory,
                    storage=storage,
                    embedding_client=embedding_client,
                    stop_event=stop_event,
                ),
                name="ingestion-worker-loop",
            ),
            asyncio.create_task(
                run_reclaim_loop(async_session_factory, stop_event=stop_event),
                name="stuck-job-reclaim-loop",
            ),
            asyncio.create_task(
                run_retention_loop(async_session_factory, storage, stop_event=stop_event),
                name="retention-sweep-loop",
            ),
        ]
        logger.info("app.worker_started", extra={"app_role": settings.app_role})

    try:
        yield
    finally:
        if background_tasks:
            stop_event.set()
            _done, pending = await asyncio.wait(background_tasks, timeout=_SHUTDOWN_GRACE_SECONDS)
            for task in pending:
                task.cancel()
            if pending:
                await asyncio.gather(*pending, return_exceptions=True)
            logger.info("app.worker_stopped")


app = FastAPI(
    title="AI Enterprise Document Intelligence System",
    version=settings.app_version,
    docs_url="/docs" if settings.resolved_enable_api_docs else None,
    redoc_url="/redoc" if settings.resolved_enable_api_docs else None,
    lifespan=lifespan,
    # T-8.1/TS-020: SCHEMA_CONTRACT.md SC-012's ErrorResponse is the only error shape, but no
    # route's own response_model names it (it's only ever constructed inside the exception
    # handlers in app/api/handlers.py, which FastAPI's OpenAPI generation can't introspect —
    # it has no visibility into what an exception handler returns). Without a reference to it
    # somewhere, ErrorResponse/ErrorCode never appear in components.schemas and
    # openapi-typescript never generates them, breaking the frontend's ErrorCode union
    # (TS-020) at the source. `"default"` (any status code not otherwise declared) is accurate
    # — every non-2xx response really is ErrorResponse-shaped — and applies app-wide in one
    # place. Per-route explicit status-code tables (API_SPEC.md §11's fuller ask, useful for
    # Swagger/ReDoc UI precision) remain a follow-up refinement, not required for this.
    responses={"default": {"model": ErrorResponse, "description": "Error envelope (SC-012)"}},
)

# API-G13: CORS allows only the configured origins; wildcard is rejected at startup (ENV-030).
# Retry-After is exposed so a rate-limited (429) response's countdown is readable cross-origin
# by the frontend (SEC-046, T-9.5).
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_allowed_origins.split(",") if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID", "Retry-After"],
)
app.add_middleware(RequestIDMiddleware)
app.add_middleware(SecurityHeadersMiddleware)

register_exception_handlers(app)

app.include_router(health_router)
app.include_router(metrics_router)
app.include_router(auth_router)
app.include_router(api_v1_router)
