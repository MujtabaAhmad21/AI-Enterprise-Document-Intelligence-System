"""Document management. API-003..API-009."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import UploadFile

from app.auth.dependencies import AdminUser, CurrentUser
from app.db.models import Document, IngestionJob
from app.db.session import get_db
from app.errors import AppError, AuthorizationError, BadRequestError
from app.middleware.rate_limit import rate_limited_by_user
from app.schemas.documents import (
    ChunkResponse,
    DocumentDetailResponse,
    DocumentResponse,
    IngestionStatusResponse,
)
from app.schemas.enums import DocumentSort, DocumentStatus, UserRole
from app.schemas.errors import ErrorCode
from app.schemas.pagination import Page
from app.services import document_service, idempotency_service, upload_validator
from app.storage.factory import get_storage

router = APIRouter(prefix="/documents", tags=["documents"])


async def document_for_delete(
    document_id: uuid.UUID,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> Document:
    """SEC-023: authorization as a dependency returning the authorised entity. API-006: check
    order is existence, then authorization (a member deleting another's document gets 403,
    since BR-011 already grants everyone read access)."""
    document = await document_service.get_document_any_state_or_404(session, document_id)
    if document.uploaded_by != user.id and UserRole(user.role) is not UserRole.ADMIN:
        raise AuthorizationError("Only the owner or an admin may delete this document.")
    return document


@router.post(
    "", status_code=status.HTTP_202_ACCEPTED, response_model=DocumentResponse,
    operation_id="create_document",
    # SEC-011b: storage/embedding cost exhaustion via mass upload.
    dependencies=[
        Depends(
            rate_limited_by_user(limit_attr="upload_rate_limit_per_hour", window_seconds=3600)
        )
    ],
)
async def upload_document(
    request: Request,
    response: Response,
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentResponse:
    # API_SPEC.md §8/T-12.2: optional Idempotency-Key, honoured only on this route. Parsed
    # before touching the (potentially large) multipart body, so a malformed key is rejected
    # cheaply.
    idempotency_key: uuid.UUID | None = None
    raw_key = request.headers.get("Idempotency-Key")
    if raw_key is not None:
        try:
            idempotency_key = uuid.UUID(raw_key)
        except ValueError as exc:
            raise BadRequestError(
                "Idempotency-Key must be a UUID.", code=ErrorCode.VALIDATION_ERROR
            ) from exc

    form = await request.form()
    parts = [v for k, v in form.multi_items() if k == "file"]
    try:
        if len(parts) != 1 or not isinstance(parts[0], UploadFile):
            raise upload_validator.malformed_upload_error()
        validated = await upload_validator.validate_upload(parts[0])
    except AppError as exc:
        # TEST-901/SEC-054: a rejected upload (bad extension/MIME/magic bytes, oversized,
        # malformed multipart, ...) is a security-relevant event, not just a 4xx to the caller.
        await document_service.record_upload_rejection(session, user, exc)
        raise

    if idempotency_key is not None:
        replay = await idempotency_service.begin(
            session, user_id=user.id, key=idempotency_key, body_hash=validated.sha256_hex
        )
        if replay is not None:
            response.headers["Idempotency-Replayed"] = "true"
            response.status_code = replay.status_code
            body = DocumentResponse.model_validate(replay.body)
            response.headers["Location"] = f"/api/v1/documents/{body.id}"
            return body

    document = await document_service.create_document(
        session, validated=validated, storage=get_storage(), user=user
    )
    response.headers["Location"] = f"/api/v1/documents/{document.id}"
    result = DocumentResponse.model_validate(document)

    if idempotency_key is not None:
        # Always 202 here (the route's own declared status): every path that could complete
        # this request with a different status raises an AppError before reaching this line,
        # and none of those are ever cached — see idempotency_service's module docstring.
        await idempotency_service.complete(
            session,
            user_id=user.id,
            key=idempotency_key,
            status_code=status.HTTP_202_ACCEPTED,
            body=result.model_dump(mode="json"),
        )

    return result


@router.get("", response_model=Page[DocumentResponse], operation_id="list_documents")
async def list_documents(
    session: Annotated[AsyncSession, Depends(get_db)],
    status_: Annotated[list[DocumentStatus] | None, Query(alias="status")] = None,
    filename: Annotated[str | None, Query(min_length=1, max_length=255)] = None,
    uploaded_by: uuid.UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
    sort: DocumentSort = DocumentSort.UPLOADED_AT_DESC,
) -> Page[DocumentResponse]:
    page = await document_service.list_documents(
        session,
        statuses=status_,
        filename=filename,
        uploaded_by=uploaded_by,
        limit=limit,
        cursor=cursor,
        sort=sort,
    )
    return Page[DocumentResponse](
        items=[DocumentResponse.model_validate(d) for d in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
        limit=limit,
    )


@router.get(
    "/{document_id}", response_model=DocumentDetailResponse, operation_id="get_document"
)
async def get_document_detail(
    document_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)]
) -> DocumentDetailResponse:
    document = await document_service.get_document_or_404(session, document_id)
    return await document_service.get_document_detail(session, document)


@router.delete(
    "/{document_id}", status_code=status.HTTP_204_NO_CONTENT, operation_id="delete_document"
)
async def delete_document(
    document: Annotated[Document, Depends(document_for_delete)],
    user: CurrentUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> None:
    await document_service.soft_delete_document(session, document, user)


@router.get(
    "/{document_id}/status", response_model=IngestionStatusResponse,
    operation_id="get_document_status",
)
async def get_ingestion_status(
    document_id: uuid.UUID, session: Annotated[AsyncSession, Depends(get_db)], response: Response
) -> IngestionStatusResponse:
    document = await document_service.get_document_or_404(session, document_id)
    job = (
        await session.execute(
            select(IngestionJob).where(
                IngestionJob.document_id == document.id,
                IngestionJob.generation == document.generation,
            )
        )
    ).scalar_one()
    response.headers["Cache-Control"] = "no-store"
    return document_service.build_ingestion_status(document, job)


@router.get(
    "/{document_id}/chunks", response_model=Page[ChunkResponse],
    operation_id="list_document_chunks",
)
async def list_document_chunks(
    document_id: uuid.UUID,
    session: Annotated[AsyncSession, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
    include_content: bool = True,
    ordinal_from: Annotated[int | None, Query(ge=0)] = None,
    ordinal_to: Annotated[int | None, Query(ge=0)] = None,
) -> Page[ChunkResponse]:
    document = await document_service.get_document_or_404(session, document_id)
    page, include = await document_service.list_chunks(
        session,
        document,
        limit=limit,
        cursor=cursor,
        include_content=include_content,
        ordinal_from=ordinal_from,
        ordinal_to=ordinal_to,
    )
    return Page[ChunkResponse](
        items=[document_service.to_chunk_response(c, include_content=include) for c in page.items],
        next_cursor=page.next_cursor,
        has_more=page.has_more,
        limit=limit,
    )


@router.post(
    "/{document_id}/reprocess",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=DocumentResponse,
    operation_id="reprocess_document",
)
async def reprocess_document(
    document_id: uuid.UUID,
    admin: AdminUser,
    session: Annotated[AsyncSession, Depends(get_db)],
) -> DocumentResponse:
    document = await document_service.get_document_for_reprocess(session, document_id)
    updated = await document_service.reprocess_document(session, document, admin)
    return DocumentResponse.model_validate(updated)
