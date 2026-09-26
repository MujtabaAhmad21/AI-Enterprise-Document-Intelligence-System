"""Application settings loaded from the environment. ENVIRONMENT.md is the defaults authority.

ENV-006: startup validation asserts cross-variable constraints (§10) so a configuration that
cannot work fails at boot, not on the first user request.
"""

import os
import sys
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.schemas.base import MAX_QUESTION_CHARS

# Known-context-window models this system is validated against (ENV-027). A model not listed
# here fails startup rather than silently skipping the budget check.
_LLM_CONTEXT_WINDOW_TOKENS = {
    "gpt-4o-mini": 128_000,
    "gpt-4o": 128_000,
}

_JWT_PLACEHOLDER_MARKERS = ("REPLACE_ME", "CHANGE_ME", "REPLACEME")


class ConfigError(Exception):
    """Raised when startup validation (§10 of ENVIRONMENT.md) fails. Named per ENV-006."""


def _apply_file_env_overrides() -> None:
    """ENV-003: any `<NAME>_FILE` pointing at a file takes precedence over `<NAME>`.

    This is how Docker secrets are consumed in production (DOP-020). Applied to raw
    process environment before Settings parses it, so it works uniformly for every field.
    """
    for name in list(os.environ):
        if not name.endswith("_FILE"):
            continue
        base_name = name[: -len("_FILE")]
        path = Path(os.environ[name])
        if path.is_file():
            os.environ[base_name] = path.read_text(encoding="utf-8").strip()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(case_sensitive=False, extra="ignore")

    # ---- 2. Core Application ----
    environment: Literal["development", "test", "staging", "production"] = "development"
    app_version: str = "0.0.0-dev"
    app_role: Literal["api", "worker", "all"] = "all"
    log_level: str = "INFO"
    enable_api_docs: bool | None = None  # None => derived from `environment` (ENV-030)
    cors_allowed_origins: str
    force_https: bool | None = None  # None => derived from `environment` (ENV-030)
    metrics_token: SecretStr | None = None
    maintenance_mode: bool = False

    # ---- 3. Database ----
    database_url: SecretStr
    postgres_user: str
    postgres_password: SecretStr
    postgres_db: str
    db_pool_size: int = 10
    db_max_overflow: int = 5
    db_pool_timeout_seconds: int = 10
    db_statement_timeout_seconds: int = 15
    db_echo: bool = False

    # ---- 4. Embeddings ----
    openai_api_key: SecretStr
    openai_base_url: str | None = None
    embedding_model: str = "text-embedding-3-small"
    embedding_dim: int = 1536
    embedding_batch_size: int = 64
    embedding_timeout_seconds: int = 20
    embedding_max_retries: int = 3

    # ---- 5. LLM ----
    llm_model: str = "gpt-4o-mini"
    # ADR-019's named fallback, used only when `answer_service._cross_document_conflict_notice`
    # detects likely cross-document conflict in retrieval: verified live (2026-09-15) that
    # `llm_model` does not reliably comply with BR-016 even given an explicit per-call notice,
    # so that one call is re-run on this stronger model instead.
    llm_conflict_escalation_model: str = "gpt-4o"
    llm_temperature: float = 0.0
    llm_seed: int = 7
    llm_max_output_tokens: int = 1200
    llm_max_context_tokens: int = 6000
    llm_timeout_seconds: int = 45
    llm_max_retries: int = 2

    # ---- 6. Retrieval & Confidence ----
    retrieval_vector_k: int = Field(default=20, ge=1, le=200)
    retrieval_keyword_k: int = Field(default=20, ge=1, le=200)
    retrieval_rrf_k: int = Field(default=60, ge=1, le=1000)
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
    retrieval_min_cosine: float = Field(default=0.30, ge=-1.0, le=1.0)
    # T-7.9/ADR-026: calibrated from real threshold-sensitivity data against the fixture
    # corpus (0.45 -> 0.50) — the highest value in the sweep that still clears SC-3's 90%
    # answerable-recall floor. See ADR-026 for the full sweep table and the recorded,
    # accepted SC-2 gap this alone does not close.
    answer_confidence_threshold: float = Field(default=0.50, ge=0.0, le=1.0)
    confidence_weight_top1: float = Field(default=0.50, ge=0.0, le=1.0)
    confidence_weight_top3: float = Field(default=0.30, ge=0.0, le=1.0)
    confidence_weight_coverage: float = Field(default=0.20, ge=0.0, le=1.0)
    confidence_coverage_target: int = Field(default=3, ge=1, le=10)
    pgvector_ef_search: int = 100
    vector_exact_scan_max_chunks: int = 5000
    max_question_chars: int = Field(default=MAX_QUESTION_CHARS, ge=1, le=8000)

    # ---- 7. Ingestion ----
    max_upload_bytes: int = 26_214_400
    max_document_pages: int = 1500
    extraction_min_chars: int = 200
    pdf_max_failed_page_ratio: float = 0.20
    chunk_target_tokens: int = 512
    chunk_overlap_tokens: int = 64
    chunk_min_tokens: int = 32
    chunk_max_tokens: int = 768
    ingestion_max_attempts: int = 3
    ingestion_backoff_base_seconds: int = 30
    ingestion_worker_concurrency: int = 2
    ingestion_stuck_after_seconds: int = 1800
    ingestion_stage_timeout_extract: int = 300
    ingestion_stage_timeout_chunk: int = 120
    ingestion_stage_timeout_embed: int = 900
    ingestion_stage_timeout_finalize: int = 60
    zip_max_entries: int = 2000
    zip_max_uncompressed_bytes: int = 209_715_200
    zip_max_ratio: int = 200

    # ---- 8. Storage ----
    storage_backend: Literal["s3", "local"] = "s3"
    storage_s3_endpoint: str | None = None
    storage_s3_region: str = "us-east-1"
    storage_s3_bucket: str | None = None
    storage_s3_access_key: SecretStr | None = None
    storage_s3_secret_key: SecretStr | None = None
    storage_local_root: str = "/var/lib/didoc/storage"
    minio_root_user: SecretStr | None = None
    minio_root_password: SecretStr | None = None

    # ---- 8.1 Retention ----
    document_file_retention_days: int = 90
    question_retention_days: int = 365
    retention_sweep_interval_hours: int = 24
    retention_sweep_batch_size: int = 500
    retention_enabled: bool = True

    # ---- 9. Auth, Rate Limits, Timeouts ----
    jwt_secret_key: SecretStr
    jwt_algorithm: Literal["HS256"] = "HS256"
    jwt_expire_minutes: int = 60
    seed_admin_password: SecretStr | None = None
    seed_member_password: SecretStr | None = None
    auth_rate_limit_per_minute: int = 10
    upload_rate_limit_per_hour: int = 30
    answer_rate_limit_per_hour: int = 60
    search_rate_limit_per_hour: int = 300
    default_rate_limit_per_hour: int = 1000
    idempotency_ttl_seconds: int = 86_400
    request_timeout_seconds: int = 75
    upload_timeout_seconds: int = 60
    answer_timeout_seconds: int = 60

    # -- derived, filled in by the validator below --
    @property
    def is_production(self) -> bool:
        return self.environment == "production"

    @property
    def resolved_enable_api_docs(self) -> bool:
        return self.enable_api_docs if self.enable_api_docs is not None else not self.is_production

    @property
    def resolved_force_https(self) -> bool:
        return self.force_https if self.force_https is not None else self.is_production

    @model_validator(mode="after")
    def _validate_startup_assertions(self) -> "Settings":
        errors: list[str] = []

        # ENV-020
        secret_key = self.jwt_secret_key.get_secret_value()
        if len(secret_key) < 32:
            errors.append("ENV-020: JWT_SECRET_KEY must be at least 32 characters.")
        if any(marker in secret_key.upper() for marker in _JWT_PLACEHOLDER_MARKERS):
            errors.append("ENV-020: JWT_SECRET_KEY looks like a placeholder value.")

        # ENV-021
        weight_sum = (
            self.confidence_weight_top1
            + self.confidence_weight_top3
            + self.confidence_weight_coverage
        )
        if abs(weight_sum - 1.0) > 1e-9:
            errors.append(
                "ENV-021: CONFIDENCE_WEIGHT_TOP1 + TOP3 + COVERAGE must equal 1.0, "
                f"got {weight_sum}."
            )

        # ENV-022 (also enforced by field constraints; kept explicit for a named error)
        if not (0.0 <= self.answer_confidence_threshold <= 1.0):
            errors.append("ENV-022: ANSWER_CONFIDENCE_THRESHOLD must be within [0, 1].")
        if not (-1.0 <= self.retrieval_min_cosine <= 1.0):
            errors.append("ENV-022: RETRIEVAL_MIN_COSINE must be within [-1, 1].")

        # ENV-023
        if not (self.chunk_min_tokens < self.chunk_target_tokens <= self.chunk_max_tokens):
            errors.append(
                "ENV-023: CHUNK_MIN_TOKENS < CHUNK_TARGET_TOKENS <= CHUNK_MAX_TOKENS violated."
            )
        if not (0 <= self.chunk_overlap_tokens < self.chunk_target_tokens):
            errors.append(
                "ENV-023: CHUNK_OVERLAP_TOKENS must be within [0, CHUNK_TARGET_TOKENS)."
            )

        # ENV-024
        if self.pgvector_ef_search < self.retrieval_vector_k:
            errors.append("ENV-024: PGVECTOR_EF_SEARCH must be >= RETRIEVAL_VECTOR_K.")

        # ENV-025 / EH-012
        if not (
            self.llm_timeout_seconds < self.answer_timeout_seconds < self.request_timeout_seconds
        ):
            errors.append(
                "ENV-025: LLM_TIMEOUT_SECONDS < ANSWER_TIMEOUT_SECONDS < REQUEST_TIMEOUT_SECONDS "
                "violated (EH-012)."
            )

        # ENV-026
        if self.max_question_chars != MAX_QUESTION_CHARS:
            errors.append(
                "ENV-026: MAX_QUESTION_CHARS must equal the QuestionStr constraint "
                f"({MAX_QUESTION_CHARS}) in SCHEMA_CONTRACT.md."
            )

        # ENV-027
        context_window = _LLM_CONTEXT_WINDOW_TOKENS.get(self.llm_model)
        if context_window is None:
            errors.append(
                f"ENV-027: unknown context window for LLM_MODEL={self.llm_model!r}; "
                "add it to _LLM_CONTEXT_WINDOW_TOKENS before deploying."
            )
        else:
            # System-prompt and max-question token budgets are approximated conservatively
            # (RAG-042); the exact prompt is asserted precisely by TEST-955 once app/llm/prompts.py
            # exists (T-6.4).
            approx_system_prompt_tokens = 1500
            approx_max_question_tokens = self.max_question_chars // 3
            required = (
                self.llm_max_context_tokens
                + approx_system_prompt_tokens
                + approx_max_question_tokens
                + self.llm_max_output_tokens
            )
            if required > context_window:
                errors.append(
                    f"ENV-027: budgeted tokens ({required}) exceed {self.llm_model}'s context "
                    f"window ({context_window})."
                )

        # Same rationale as ENV-027, for the conflict-escalation model: a call that escalates
        # into an unknown context window is worse than one that never escalates at all.
        if self.llm_conflict_escalation_model not in _LLM_CONTEXT_WINDOW_TOKENS:
            errors.append(
                "unknown context window for LLM_CONFLICT_ESCALATION_MODEL="
                f"{self.llm_conflict_escalation_model!r}; add it to "
                "_LLM_CONTEXT_WINDOW_TOKENS before deploying."
            )

        # ENV-028 / ENV-029: require a live database connection (schema_metadata,
        # document_chunks.embedding typmod, and DISTINCT embedding_model). These are readiness
        # checks, not startup-config checks — see DATABASE.md §6 and IMPLEMENTATION_PLAN T-2.9.

        # ENV-030 / ENV-036
        if self.is_production:
            if self.resolved_enable_api_docs:
                errors.append("ENV-030: ENABLE_API_DOCS must be false in production.")
            if self.db_echo:
                errors.append("ENV-030: DB_ECHO must be false in production.")
            if not self.resolved_force_https:
                errors.append("ENV-030: FORCE_HTTPS must be true in production.")
            if "*" in {o.strip() for o in self.cors_allowed_origins.split(",")}:
                errors.append("ENV-030: CORS_ALLOWED_ORIGINS must not contain '*' in production.")
            if self.storage_backend != "s3":
                errors.append("ENV-036: STORAGE_BACKEND must be 's3' in production.")

        # ENV-031
        if self.storage_backend == "s3":
            missing = [
                name
                for name, value in (
                    ("STORAGE_S3_ENDPOINT", self.storage_s3_endpoint),
                    ("STORAGE_S3_BUCKET", self.storage_s3_bucket),
                    ("STORAGE_S3_ACCESS_KEY", self.storage_s3_access_key),
                    ("STORAGE_S3_SECRET_KEY", self.storage_s3_secret_key),
                )
                if not value
            ]
            if missing:
                errors.append(
                    "ENV-031: STORAGE_BACKEND=s3 requires " + ", ".join(missing) + "."
                )

        # ENV-037
        if self.document_file_retention_days < 1:
            errors.append("ENV-037: DOCUMENT_FILE_RETENTION_DAYS must be >= 1.")
        if self.question_retention_days < 1:
            errors.append("ENV-037: QUESTION_RETENTION_DAYS must be >= 1.")

        if errors:
            raise ConfigError("Invalid configuration:\n" + "\n".join(f"  - {e}" for e in errors))

        return self


def load_settings() -> Settings:
    """Build Settings from the environment, applying ENV-003 file overrides first.

    On failure, prints the named error(s) and exits non-zero (ENV-006) rather than raising
    into an ASGI server that would otherwise start half-configured.
    """
    _apply_file_env_overrides()
    try:
        return Settings()
    except ConfigError as exc:
        print(f"FATAL: {exc}", file=sys.stderr)
        sys.exit(1)


settings = load_settings()
