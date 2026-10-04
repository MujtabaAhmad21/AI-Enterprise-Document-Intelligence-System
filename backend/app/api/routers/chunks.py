"""T-7.6: citation resolution. API-014, API-015."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.errors import NotFoundError
from app.schemas.documents import (
    ChunkSourceResponse,
    CitationResolveRequest,
    CitationResolveResponse,
)
from app.schemas.errors import ErrorCode
from app.services import citation_resolution_service

chunks_router = APIRouter(prefix="/chunks", tags=["citations"])
citations_router = APIRouter(prefix="/citations", tags=["citations"])


@chunks_router.get(
    "/{chunk_id}", response_model=ChunkSourceResponse, operation_id="get_chunk_source"
)
async def get_chunk(
    chunk_id: UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    context_window: Annotated[int, Query(ge=0, le=3)] = 0,
) -> ChunkSourceResponse:
    resolved = await citation_resolution_service.resolve_chunk(
        session, chunk_id, context_window=context_window
    )
    if resolved is None:
        raise NotFoundError("Chunk not found.", code=ErrorCode.CHUNK_NOT_FOUND)
    return resolved


@citations_router.post(
    "/resolve", response_model=CitationResolveResponse, operation_id="resolve_citations"
)
async def resolve_citations(
    body: CitationResolveRequest, session: Annotated[AsyncSession, Depends(get_db)]
) -> CitationResolveResponse:
    items, missing = await citation_resolution_service.resolve_chunks(
        session, body.chunk_ids, context_window=body.context_window
    )
    return CitationResolveResponse(items=items, missing=missing)
