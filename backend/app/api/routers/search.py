"""Hybrid search. API-010. FR-036: never constructs an LLM client."""

import time
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.db.session import get_db
from app.middleware.rate_limit import rate_limited_by_user
from app.providers.base import EmbeddingClient
from app.providers.factory import get_embedding_client
from app.schemas.search import SearchRequest, SearchResponse
from app.services import retrieval_service

router = APIRouter(prefix="/search", tags=["search"])


@router.post(
    "",
    response_model=SearchResponse,
    operation_id="search",
    # SEC-011d: embedding cost via search flooding.
    dependencies=[
        Depends(
            rate_limited_by_user(limit_attr="search_rate_limit_per_hour", window_seconds=3600)
        )
    ],
)
async def search(
    body: SearchRequest,
    _user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    embedding_client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
) -> SearchResponse:
    """`embedding_client` is `Depends`-injected (rather than called directly, unlike
    `storage.factory.get_storage()` elsewhere) so tests can substitute a fake via
    `app.dependency_overrides` — T-001, every non-provider test uses a fake, never the real
    OpenAI client."""
    started_at = time.monotonic()
    outcome = await retrieval_service.retrieve(
        session,
        embedding_client=embedding_client,
        query=body.query,
        document_ids=body.document_ids,
        top_k=body.top_k,
        min_similarity=body.min_similarity,
    )
    # SR-014/SR-021: search returns R_conf unfiltered — every candidate similarity as found,
    # never gated. Only API-011 (Phase 6) refuses.
    results = await retrieval_service.build_search_results(session, outcome.r_conf)
    latency_ms = int((time.monotonic() - started_at) * 1000)

    return SearchResponse(
        query=body.query,
        normalized_query=outcome.normalized_query,
        top_k=body.top_k,
        returned=len(results),
        candidate_count=outcome.candidate_count,
        embedding_model=outcome.embedding_model,
        latency_ms=latency_ms,
        results=results,
    )
