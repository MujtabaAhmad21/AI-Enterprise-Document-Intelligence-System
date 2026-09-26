"""Structured JSON logging. OBS-001..OBS-011.

Every log line is a single JSON object on stdout carrying request_id/job_id and the
other correlation identifiers from a contextvars-based context (OBS-011): manual
threading of request_id through every function call is prohibited.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar, Token
from datetime import UTC, datetime
from typing import Any

# ---- OBS-011: contextvars-based correlation context ----

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
_job_id: ContextVar[str | None] = ContextVar("job_id", default=None)
_user_id: ContextVar[str | None] = ContextVar("user_id", default=None)
_document_id: ContextVar[str | None] = ContextVar("document_id", default=None)
_answer_id: ContextVar[str | None] = ContextVar("answer_id", default=None)
_trace_id: ContextVar[str | None] = ContextVar("trace_id", default=None)
_span_id: ContextVar[str | None] = ContextVar("span_id", default=None)

_CONTEXT_VARS: dict[str, ContextVar[str | None]] = {
    "request_id": _request_id,
    "job_id": _job_id,
    "user_id": _user_id,
    "document_id": _document_id,
    "answer_id": _answer_id,
    "trace_id": _trace_id,
    "span_id": _span_id,
}


class LogContext:
    """Set/reset one correlation identifier for the current async task (OBS-003, OBS-011)."""

    @staticmethod
    def set(**fields: str | None) -> dict[str, Token[str | None]]:
        tokens: dict[str, Token[str | None]] = {}
        for name, value in fields.items():
            var = _CONTEXT_VARS[name]
            tokens[name] = var.set(value)
        return tokens

    @staticmethod
    def reset(tokens: dict[str, Token[str | None]]) -> None:
        for name, token in tokens.items():
            _CONTEXT_VARS[name].reset(token)

    @staticmethod
    def get(name: str) -> str | None:
        return _CONTEXT_VARS[name].get()


class ContextFilter(logging.Filter):
    """Injects the current correlation identifiers onto every LogRecord (OBS-002, OBS-011)."""

    def filter(self, record: logging.LogRecord) -> bool:
        for name, var in _CONTEXT_VARS.items():
            value = var.get()
            if value is not None:
                setattr(record, name, value)
        return True


# Attributes stdlib logging.LogRecord always has; anything else on the record is caller-supplied
# structured data passed via `extra=` and belongs in the JSON payload (OBS-002's "aggregates" vs
# "individual events" distinction lives at the metrics layer, not here).
_STANDARD_RECORD_ATTRS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__) | {
    "message",
    "asctime",
}


# SEC-053: a backstop, not the primary control. SEC-012's actual guarantee — document text,
# chunk content, quoted_span, prompts, provider bodies, passwords, and tokens are never passed
# to a logger.*() call in the first place — is enforced by review at each of this codebase's
# handful of call sites (audited for Phase 9, T-9.7), not by this filter. This only catches an
# obvious secret-shaped string that slips through anyway.
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"Bearer\s+\S+"),
    re.compile(r"eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+"),
)


def _redact(value: Any) -> Any:
    if isinstance(value, str):
        for pattern in _SECRET_PATTERNS:
            value = pattern.sub("[REDACTED]", value)
        return value
    if isinstance(value, dict):
        return {k: _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(v) for v in value]
    return value


class JSONFormatter(logging.Formatter):
    """One JSON object per line. OBS-007, OBS-008."""

    def __init__(self, *, service: str, version: str, environment: str) -> None:
        super().__init__()
        self._service = service
        self._version = version
        self._environment = environment

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": _redact(record.getMessage()),
            "service": self._service,
            "version": self._version,
            "environment": self._environment,
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS or key in payload:
                continue
            payload[key] = _redact(value)
        if record.exc_info:
            # OBS-010: the traceback is logged server-side only; EH-010/EH-003 keep it out of
            # every client-facing response body.
            payload["exc_info"] = _redact(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(*, level: str, service: str, version: str, environment: str) -> None:
    """Replace the root logger's handlers with a single JSON-on-stdout handler (OBS-001)."""
    root = logging.getLogger()
    root.setLevel(level.upper())
    for handler in list(root.handlers):
        root.removeHandler(handler)

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(JSONFormatter(service=service, version=version, environment=environment))
    handler.addFilter(ContextFilter())
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
