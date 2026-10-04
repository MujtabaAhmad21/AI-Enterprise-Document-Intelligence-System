"""Health endpoints. API-016, API-017. Outside /api/v1 so probes never depend on the
versioned surface (API-G01).

ARCHITECTURE.md §4.1's dependency graph draws routers.health -> Database session directly,
skipping the service layer other routers go through: a health probe is infrastructure, not a
business operation, so there is no service to own it.
"""

import time
from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.db.checks import run_readiness_checks
from app.db.session import get_db
from app.schemas.base import APIModel

router = APIRouter(tags=["health"])

_process_started_at = time.monotonic()


class LivenessResponse(APIModel):
    status: str
    uptime_seconds: int


class ReadinessChecks(APIModel):
    database: bool
    vector_extension: bool
    migrations_current: bool
    embedding_dimension: bool
    embedding_model_match: bool
    vector_index: bool


class ReadinessResponse(APIModel):
    status: str
    checks: ReadinessChecks
    embedding_model: str
    embedding_dim: int
    migration_revision: str | None
    version: str


@router.get("/health/live", response_model=LivenessResponse, operation_id="get_liveness")
async def liveness() -> LivenessResponse:
    return LivenessResponse(
        status="alive", uptime_seconds=int(time.monotonic() - _process_started_at)
    )


@router.get("/health/ready", response_model=ReadinessResponse, operation_id="get_readiness")
async def readiness(
    response: Response, session: Annotated[AsyncSession, Depends(get_db)]
) -> ReadinessResponse:
    result = await run_readiness_checks(session)
    if not result.ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ready" if result.ready else "not_ready",
        checks=ReadinessChecks(
            database=result.database,
            vector_extension=result.vector_extension,
            migrations_current=result.migrations_current,
            embedding_dimension=result.embedding_dimension,
            embedding_model_match=result.embedding_model_match,
            vector_index=result.vector_index,
        ),
        embedding_model=settings.embedding_model,
        embedding_dim=settings.embedding_dim,
        migration_revision=result.migration_revision,
        version=settings.app_version,
    )
