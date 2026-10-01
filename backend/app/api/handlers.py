"""Canonical error envelope: the 7 registered exception handlers. ERROR_HANDLING.md §4.

EH-001: every non-2xx response, including FastAPI's own validation errors and unhandled
exceptions, is an ErrorResponse. Registered in the order below; the first matching handler wins.
"""

import logging
import uuid
from datetime import UTC, datetime

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError, ResponseValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError, IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.errors import AppError, RateLimitError
from app.logging import get_logger
from app.schemas.errors import ErrorBody, ErrorCode, ErrorDetail, ErrorResponse

logger = get_logger(__name__)

# ERROR_HANDLING.md §5 — constraint name -> (code, http_status). An unmapped IntegrityError is
# deliberately INTERNAL_ERROR: a silent mapping to 409 would hide a real bug (EH-011).
_CONSTRAINT_MAP: dict[str, tuple[ErrorCode, int]] = {
    "uq_documents_content_hash_live": (ErrorCode.DUPLICATE_DOCUMENT, status.HTTP_409_CONFLICT),
    "uq_jobs_document_generation": (
        ErrorCode.INGESTION_IN_PROGRESS,
        status.HTTP_409_CONFLICT,
    ),
    "uq_users_email": (ErrorCode.VALIDATION_ERROR, status.HTTP_422_UNPROCESSABLE_CONTENT),
    "ck_answers_confidence_gate": (
        ErrorCode.INTERNAL_ERROR,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
    "ck_answers_refusal_shape": (
        ErrorCode.INTERNAL_ERROR,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
    "ck_answers_answered_shape": (
        ErrorCode.INTERNAL_ERROR,
        status.HTTP_500_INTERNAL_SERVER_ERROR,
    ),
}

_GENERIC_MESSAGES: dict[ErrorCode, str] = {
    ErrorCode.DUPLICATE_DOCUMENT: "A live document with identical content already exists.",
    ErrorCode.INGESTION_IN_PROGRESS: "This document is not in a terminal ingestion state.",
    ErrorCode.VALIDATION_ERROR: "Request validation failed.",
    ErrorCode.INTERNAL_ERROR: "An internal error occurred.",
    ErrorCode.DATABASE_UNAVAILABLE: "The database is temporarily unavailable.",
}


def _request_id(request: Request) -> uuid.UUID:
    raw = getattr(request.state, "request_id", None)
    return uuid.UUID(raw) if raw else uuid.uuid4()


def _envelope(
    *,
    code: ErrorCode,
    message: str,
    request_id: uuid.UUID,
    details: list[ErrorDetail] | dict[str, object] | None = None,
) -> ErrorResponse:
    return ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details,
            request_id=request_id,
            timestamp=datetime.now(UTC),
        )
    )


def _json_response(
    status_code: int,
    body: ErrorResponse,
    request_id: uuid.UUID,
    *,
    extra_headers: dict[str, str] | None = None,
) -> JSONResponse:
    headers = {"X-Request-ID": str(request_id)}
    if extra_headers:
        headers.update(extra_headers)
    return JSONResponse(
        status_code=status_code, content=body.model_dump(mode="json"), headers=headers
    )


# ---- Handler 1: AppError ----


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    request_id = _request_id(request)
    logger.log(
        exc.log_level,
        "http.error",
        extra={"error_code": exc.code.value, "http_status": exc.http_status},
    )
    body = _envelope(code=exc.code, message=exc.message, request_id=request_id, details=exc.details)
    extra_headers = None
    if isinstance(exc, RateLimitError):
        extra_headers = {"Retry-After": str(exc.retry_after_seconds)}
    return _json_response(exc.http_status, body, request_id, extra_headers=extra_headers)


# ---- Handler 2: FastAPI RequestValidationError ----


async def request_validation_error_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    request_id = _request_id(request)
    details = [
        ErrorDetail(field=".".join(str(p) for p in err["loc"]), issue=err["msg"])
        for err in exc.errors()
    ]
    logger.warning("http.validation_error", extra={"field_count": len(details)})
    body = _envelope(
        code=ErrorCode.VALIDATION_ERROR,
        message=_GENERIC_MESSAGES[ErrorCode.VALIDATION_ERROR],
        request_id=request_id,
        details=details,
    )
    return _json_response(status.HTTP_422_UNPROCESSABLE_CONTENT, body, request_id)


# ---- Handler 3: FastAPI ResponseValidationError ----


async def response_validation_error_handler(
    request: Request, exc: ResponseValidationError
) -> JSONResponse:
    request_id = _request_id(request)
    # EH-009: the server produced a response violating its own contract (e.g. SC-017). This is
    # always a defect, never a partially-valid answer, and is alerted on.
    logger.error("http.response_contract_violation", exc_info=exc)
    body = _envelope(
        code=ErrorCode.INTERNAL_ERROR,
        message=_GENERIC_MESSAGES[ErrorCode.INTERNAL_ERROR],
        request_id=request_id,
    )
    return _json_response(status.HTTP_500_INTERNAL_SERVER_ERROR, body, request_id)


# ---- Handler 4: sqlalchemy.exc.IntegrityError ----


def _map_integrity_error(exc: IntegrityError) -> tuple[ErrorCode, int]:
    diag = getattr(exc.orig, "diag", None)
    constraint_name = getattr(diag, "constraint_name", None)
    if constraint_name and constraint_name in _CONSTRAINT_MAP:
        return _CONSTRAINT_MAP[constraint_name]
    table_name = getattr(diag, "table_name", None)
    if table_name == "answer_citations":
        return (ErrorCode.INTERNAL_ERROR, status.HTTP_500_INTERNAL_SERVER_ERROR)
    return (ErrorCode.INTERNAL_ERROR, status.HTTP_500_INTERNAL_SERVER_ERROR)


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    request_id = _request_id(request)
    code, http_status = _map_integrity_error(exc)
    log_level = logging.ERROR if code is ErrorCode.INTERNAL_ERROR else logging.WARNING
    # EH-010: the exception text goes to the log with the request_id; never to the client.
    logger.log(log_level, "db.integrity_error", exc_info=exc)
    body = _envelope(code=code, message=_GENERIC_MESSAGES[code], request_id=request_id)
    return _json_response(http_status, body, request_id)


# ---- Handler 5: sqlalchemy OperationalError / DBAPIError ----


async def database_unavailable_handler(
    request: Request, exc: OperationalError | DBAPIError
) -> JSONResponse:
    request_id = _request_id(request)
    logger.error("db.unavailable", exc_info=exc)
    body = _envelope(
        code=ErrorCode.DATABASE_UNAVAILABLE,
        message=_GENERIC_MESSAGES[ErrorCode.DATABASE_UNAVAILABLE],
        request_id=request_id,
    )
    return _json_response(status.HTTP_503_SERVICE_UNAVAILABLE, body, request_id)


# ---- Handler 6: starlette.HTTPException ----


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    request_id = _request_id(request)
    code = ErrorCode.INTERNAL_ERROR
    if exc.status_code == status.HTTP_404_NOT_FOUND:
        code = ErrorCode.DOCUMENT_NOT_FOUND
    elif exc.status_code == status.HTTP_401_UNAUTHORIZED:
        code = ErrorCode.UNAUTHENTICATED
    elif exc.status_code == status.HTTP_403_FORBIDDEN:
        code = ErrorCode.FORBIDDEN
    logger.warning("http.exception", extra={"http_status": exc.status_code})
    message = exc.detail if isinstance(exc.detail, str) else _GENERIC_MESSAGES.get(code, "Error.")
    body = _envelope(code=code, message=message, request_id=request_id)
    return _json_response(exc.status_code, body, request_id)


# ---- Handler 7: catch-all ----


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    # EH-003/EH-010: full traceback logged server-side only, never in the response body.
    logger.error("http.unhandled_exception", exc_info=exc)
    body = _envelope(
        code=ErrorCode.INTERNAL_ERROR,
        message=_GENERIC_MESSAGES[ErrorCode.INTERNAL_ERROR],
        request_id=request_id,
    )
    return _json_response(status.HTTP_500_INTERNAL_SERVER_ERROR, body, request_id)


def register_exception_handlers(app: FastAPI) -> None:
    """Registers all 7 handlers in the order mandated by ERROR_HANDLING.md §4."""
    app.add_exception_handler(AppError, app_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(ResponseValidationError, response_validation_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(IntegrityError, integrity_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(OperationalError, database_unavailable_handler)  # type: ignore[arg-type]
    app.add_exception_handler(DBAPIError, database_unavailable_handler)  # type: ignore[arg-type]
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # type: ignore[arg-type]
    app.add_exception_handler(Exception, unhandled_exception_handler)
