"""Domain exception hierarchy. ERROR_HANDLING.md §1-§2.

EH-007: services raise these; only the HTTP layer (app/api/handlers.py) knows
about status codes. No service imports fastapi.HTTPException.
"""

import logging

from app.schemas.enums import IngestionFailureCode
from app.schemas.errors import ErrorCode, ErrorDetail


class AppError(Exception):
    """Base for every typed application error."""

    code: ErrorCode
    http_status: int
    log_level: int = logging.WARNING

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        details: list[ErrorDetail] | dict[str, object] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.details = details
        if code is not None:
            self.code = code


# ---- 4xx — the caller can fix it ----


class BadRequestError(AppError):
    """MALFORMED_UPLOAD / INVALID_CURSOR — pass `code=`.

    Not in ERROR_HANDLING.md §2's exception-hierarchy code block (which has no 4xx entry below
    422), but §3.1's catalogue lists both codes at 400, so a class carrying that status is
    needed; it follows the same "shared status, code passed at the call site" pattern as
    NotFoundError/ConflictError above.
    """

    http_status = 400


class ValidationError(AppError):
    code = ErrorCode.VALIDATION_ERROR
    http_status = 422


class AuthenticationError(AppError):
    """UNAUTHENTICATED (default) or INVALID_CREDENTIALS (login) — pass `code=` to override."""

    code = ErrorCode.UNAUTHENTICATED
    http_status = 401


class AuthorizationError(AppError):
    code = ErrorCode.FORBIDDEN
    http_status = 403


class NotFoundError(AppError):
    """DOCUMENT_NOT_FOUND / ANSWER_NOT_FOUND / CHUNK_NOT_FOUND — pass `code=` at the call site."""

    http_status = 404


class ConflictError(AppError):
    """DUPLICATE_DOCUMENT / INGESTION_IN_PROGRESS / ORIGINAL_FILE_PURGED / IDEMPOTENCY_* —
    pass `code=`."""

    http_status = 409


class PayloadTooLargeError(AppError):
    code = ErrorCode.PAYLOAD_TOO_LARGE
    http_status = 413


class UnsupportedMediaTypeError(AppError):
    code = ErrorCode.UNSUPPORTED_MEDIA_TYPE
    http_status = 415


class RateLimitError(AppError):
    """SEC-046: `retry_after_seconds` is surfaced as the `Retry-After` response header by
    `app/api/handlers.py`'s `app_error_handler` — never remaining quota or another user's
    consumption."""

    code = ErrorCode.RATE_LIMITED
    http_status = 429

    def __init__(
        self,
        message: str,
        *,
        code: ErrorCode | None = None,
        details: list[ErrorDetail] | dict[str, object] | None = None,
        retry_after_seconds: int,
    ) -> None:
        super().__init__(message, code=code, details=details)
        self.retry_after_seconds = retry_after_seconds


# ---- 5xx — the caller cannot fix it ----


class UpstreamError(AppError):
    """EMBEDDING_PROVIDER_ERROR / LLM_PROVIDER_ERROR / LLM_INVALID_OUTPUT / LLM_CONTENT_FILTERED —
    pass `code=`."""

    http_status = 502


class UpstreamTimeoutError(AppError):
    """EMBEDDING_TIMEOUT / LLM_TIMEOUT — pass `code=`."""

    http_status = 504


class DependencyUnavailableError(AppError):
    """DATABASE_UNAVAILABLE / STORAGE_UNAVAILABLE / VECTOR_* / MIGRATIONS_PENDING — pass `code=`."""

    http_status = 503


class InternalError(AppError):
    code = ErrorCode.INTERNAL_ERROR
    http_status = 500
    log_level = logging.ERROR


class IngestionError(Exception):
    """Deliberately outside AppError (EH-008): ingestion runs after the HTTP response was
    already sent (AP-6), so its failures are recorded as document/job state
    (INGESTION_SPEC.md §9), never returned to an HTTP caller."""

    def __init__(
        self, failure_code: IngestionFailureCode, message: str, *, retryable: bool
    ) -> None:
        super().__init__(message)
        self.failure_code = failure_code
        self.message = message
        self.retryable = retryable
