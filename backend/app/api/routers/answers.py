"""Grounded Q&A. API-011..013."""

import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import CurrentUser
from app.db.session import get_db
from app.errors import NotFoundError
from app.middleware.rate_limit import rate_limited_by_user
from app.providers.base import EmbeddingClient, LLMClient
from app.providers.factory import get_embedding_client, get_llm_client, get_llm_escalation_client
from app.schemas.answers import AnswerRequest, AnswerResponse, AnswerSummary
from app.schemas.enums import AnswerStatus
from app.schemas.errors import ErrorCode
from app.schemas.pagination import Page
from app.services import answer_service

router = APIRouter(prefix="/answers", tags=["answers"])


@router.post(
    "",
    response_model=AnswerResponse,
    operation_id="create_answer",
    # SEC-011c: LLM cost exhaustion via question flooding.
    dependencies=[
        Depends(
            rate_limited_by_user(limit_attr="answer_rate_limit_per_hour", window_seconds=3600)
        )
    ],
)
async def create_answer(
    body: AnswerRequest,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
    embedding_client: Annotated[EmbeddingClient, Depends(get_embedding_client)],
    llm_client: Annotated[LLMClient, Depends(get_llm_client)],
    escalation_llm_client: Annotated[LLMClient, Depends(get_llm_escalation_client)],
) -> AnswerResponse:
    """API-011. A refusal is `200`, not an error — clients branch on `status`, never on HTTP
    code (API_SPEC.md's own words)."""
    return await answer_service.answer_question(
        session,
        user=user,
        embedding_client=embedding_client,
        llm_client=llm_client,
        escalation_llm_client=escalation_llm_client,
        question=body.question,
        document_ids=body.document_ids,
        top_k=body.top_k,
    )


@router.get("", response_model=Page[AnswerSummary], operation_id="list_answers")
async def list_answers(
    session: Annotated[AsyncSession, Depends(get_db)],
    status_: Annotated[AnswerStatus | None, Query(alias="status")] = None,
    asked_by: uuid.UUID | None = None,
    created_after: datetime | None = None,
    created_before: datetime | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
) -> Page[AnswerSummary]:
    return await answer_service.list_answers(
        session,
        status=status_,
        asked_by=asked_by,
        created_after=created_after,
        created_before=created_before,
        limit=limit,
        cursor=cursor,
    )


@router.get("/{answer_id}", response_model=AnswerResponse, operation_id="get_answer")
async def get_answer(
    answer_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> AnswerResponse:
    """API-013 (FR-025)."""
    response = await answer_service.get_answer_response(session, answer_id)
    if response is None:
        raise NotFoundError("Answer not found.", code=ErrorCode.ANSWER_NOT_FOUND)
    return response
