<div align="center">

# AI Enterprise Document Intelligence System

**Grounded, cited answers from your organisation's own documents, with a deterministic refusal when the evidence isn't there.**

[![Live demo](https://img.shields.io/badge/demo-live-2ea44f?style=flat-square&logo=vercel&logoColor=white)](https://ai-enterprise-document-intelligence.vercel.app/documents)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688?style=flat-square&logo=fastapi&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-v2-E92063?style=flat-square&logo=pydantic&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16%20%2B%20pgvector-4169E1?style=flat-square&logo=postgresql&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-15-000000?style=flat-square&logo=nextdotjs&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?style=flat-square&logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?style=flat-square&logo=typescript&logoColor=white)
![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-06B6D4?style=flat-square&logo=tailwindcss&logoColor=white)
![OpenAI](https://img.shields.io/badge/OpenAI-embeddings%20%2B%20chat-412991?style=flat-square&logo=openai&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-Compose-2496ED?style=flat-square&logo=docker&logoColor=white)

[**Live demo**](https://ai-enterprise-document-intelligence.vercel.app/documents) ·
[Quick start](#quick-start) ·
[Security](#security-first-and-fully-guardrailed) ·
[Architecture](#architecture) ·
[Limitations](#roadmap-and-known-limitations)

</div>

<!-- INCREMENTAL-PUBLISH-NOTE:START (remove this block once the full source is published) -->
> [!NOTE]
> **The source is being published incrementally.** This repository is filled in file by file, so
> some paths, commands and features described below may not exist here yet. The full codebase
> will be available soon. Until then, the README describes the complete system.
<!-- INCREMENTAL-PUBLISH-NOTE:END -->

---

## Table of contents

- [Why this exists](#why-this-exists)
- [Live demo](#live-demo)
- [Key features](#key-features)
- [How an answer is produced](#how-an-answer-is-produced)
- [Security-first and fully guardrailed](#security-first-and-fully-guardrailed)
- [Reliability and fallbacks](#reliability-and-fallbacks)
- [Architecture](#architecture)
- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
- [Production deployment](#production-deployment)
- [Local development without Docker](#local-development-without-docker)
- [Configuration reference](#configuration-reference)
- [API overview](#api-overview)
- [Testing and quality gates](#testing-and-quality-gates)
- [Measured results](#measured-results)
- [Project structure](#project-structure)
- [Roadmap and known limitations](#roadmap-and-known-limitations)
- [Contributing](#contributing)
- [License](#license)
- [Author](#author)

---

## Why this exists

Enterprises collect hundreds or thousands of unstructured documents: compliance PDFs, contracts,
technical manuals, policy handbooks. Answering one factual question, such as *"What is the notice
period for termination in the Acme MSA?"*, still means a person has to find the right document,
skim it, and check the passage by hand.

The usual ways of automating this fail in one of two ways:

1. **Keyword search** returns documents, not answers, and misses the same idea phrased differently.
2. **Ungrounded LLM assistants** write fluent answers that can't be checked and are sometimes made
   up. In compliance and contract work, an answer you can't verify is worse than no answer,
   because it sounds authoritative.

This system answers **only** from retrieved document evidence. It attaches a checkable citation
to every factual claim, and it **refuses by deterministic arithmetic** when the evidence is too
weak. The model is never asked whether it can answer.

**Who it's for:** organisations that need grounded, cited answers over their internal documents,
where a person must be able to check where every statement came from. Typical users include:

| Persona | Role | Need |
|---|---|---|
| Compliance analyst | `member` | Find and cite the exact clause behind a regulatory position |
| Legal ops coordinator | `member` | Upload contract batches and confirm they're searchable |
| Field engineer | `member` | Ask plain-language questions of technical manuals |
| Knowledge-base administrator | `admin` | Remove outdated documents, reprocess failures, watch pipeline health |

---

## Live demo

**https://ai-enterprise-document-intelligence.vercel.app/documents**

The public demo is a **frontend-only build** (`NEXT_PUBLIC_DEMO_MODE=true`). No backend is
connected. Every screen can be browsed, and visitors are signed in automatically as a demo
`member`. Uploading, search and answers are switched off, because they use paid OpenAI credits:
the API client refuses every request in the browser before anything is sent. To use the full
pipeline, run the stack yourself with your own API key ([Quick start](#quick-start)).

---

## Key features

- **Document ingestion (PDF and DOCX).** Upload is validated. Text is extracted with page numbers
  (PDF) and heading hierarchy (DOCX), normalised the same way every time, chunked with a token
  budget along the document's structure (LlamaIndex utilities, 512-token target, 64-token
  overlap), embedded in batches, and indexed. All of this runs in an asynchronous worker backed
  by database job records.
- **Hybrid retrieval.** Vector search with a pgvector HNSW index and cosine similarity runs
  alongside PostgreSQL full-text search (a generated `tsvector` column with a GIN index). The two
  result lists are combined with **Reciprocal Rank Fusion**, with fixed tie-breaking so the same
  query always returns the same order.
- **Deterministic confidence gate.** A pure function of retrieval scores (top-1 similarity, mean
  of the top 3, coverage), computed with `Decimal` arithmetic, decides *answer or refuse*
  **before** any LLM call. The refusal path makes no LLM call and uses no tokens.
- **Citation-enforced answers.** The LLM (`gpt-4o-mini` by default) must return strict,
  schema-validated JSON. Every claim cites chunk IDs, and each citation is checked on the server
  by set membership and a verbatim quote match. An answer left with no valid citations becomes a
  refusal.
- **Conflict handling.** If passages from different documents score almost the same, the model
  is told to present both positions with separate citations. That call is also escalated to a
  stronger model (`gpt-4o` by default).
- **Citation inspection.** Each inline `[n]` marker opens the exact source chunk text with its
  document, page and section. Citations to documents deleted later still resolve, using the
  metadata kept at answer time.
- **Passage search without an LLM.** `POST /api/v1/search` returns ranked chunks with vector,
  keyword, fused and cosine scores. It never calls the model.
- **Document scoping.** Questions can be limited to chosen documents. The filter is applied
  inside the SQL query, not after retrieval.
- **Full audit trail.** Answers can't be changed once saved. Each one stores the question,
  confidence report, retrieval trace, model, token usage and latency, so it can be explained
  later without running the pipeline again.
- **Data retention.** A daily sweep deletes the original files of documents soft-deleted more than
  90 days ago and redacts question text older than 365 days. Chunks, answers, citations and audit
  rows are kept.
- **Web app.** A Next.js App Router UI with document list, detail and upload, live ingestion
  progress, Ask, passage search, and answer history. It supports light and dark themes.
- **API contract kept in sync.** Pydantic v2 generates the OpenAPI schema, and the schema
  generates the TypeScript types and Zod schemas. CI fails if the generated files drift.

---

## How an answer is produced

```mermaid
flowchart TD
    Q["Question"] --> V["Validate<br/>(non-empty, max 2,000 chars)"]
    V --> R["Hybrid retrieval<br/>pgvector HNSW + PostgreSQL FTS"]
    R --> F["Reciprocal Rank Fusion<br/>deterministic tie-break"]
    F --> G{"Confidence gate<br/>pure arithmetic on scores"}
    G -- "below threshold" --> X["Refusal: insufficient_context<br/>fixed template, 0 citations,<br/>NO LLM call"]
    G -- "at or above threshold" --> D["Re-check for documents<br/>deleted mid-request"]
    D --> A["Assemble context<br/>token-budgeted, whole chunks,<br/>XML-escaped chunk elements"]
    A --> C{"Near-tied passages from<br/>different documents?"}
    C -- "no" --> L1["LLM: gpt-4o-mini<br/>strict JSON schema"]
    C -- "yes" --> L2["Conflict notice +<br/>escalate to gpt-4o"]
    L1 --> CV["Citation validator<br/>set membership + verbatim span match"]
    L2 --> CV
    CV -- "no valid citations" --> X2["Refusal: NO_VALID_CITATIONS"]
    CV -- "valid" --> P["Persist immutable answer<br/>+ citations + trace + audit event"]
```

---

## Security-first and fully guardrailed

The threat model in one sentence: *the system takes in files an attacker can control and passes
text from them to a language model whose output users will treat as authoritative.* Every
control below is implemented in code and backed by tests (`backend/tests/security`,
`backend/tests/failure`, and others).

### Authentication and sessions

| Control | Implementation |
|---|---|
| JWT on every API route | A router-level dependency requires `Authorization: Bearer <jwt>` on every `/api/v1/*` route except `POST /api/v1/auth/token`, so new routes are protected by default. A test enumerates the OpenAPI document and asserts `401` for every route. |
| Algorithm pinning | Tokens are HS256 JWTs (`sub`, `role`, `iat`, `exp`, `jti`, 60-minute TTL). `HS256` is the only algorithm allowed on decode, so `alg: none` and algorithm-confusion tokens are rejected. |
| Password hashing | **Argon2id** (`time_cost=3`, `memory_cost=64 MiB`, `parallelism=4`) via `argon2-cffi`. |
| No user enumeration | Unknown email and wrong password fail the same way. The unknown-user path verifies a dummy hash so response timing gives nothing away. Inactive users fail the same way too. |
| Browser session | The token is stored in an **httpOnly, SameSite=Lax** cookie (`Secure` in production) set by a Next.js route handler. It is never kept in `localStorage`. |
| Security headers | The API sends `X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer`, and HSTS in production. The web app sends a **per-request nonce CSP** (`default-src 'self'`, `script-src 'nonce-…' 'strict-dynamic'`, `frame-ancestors 'none'`, no `unsafe-inline` scripts). |

### Authorisation

| Control | Implementation |
|---|---|
| Two roles, checked on the server | Exactly `admin` and `member`, enforced by an enum and a DB check constraint. The role comes only from the validated JWT claim, never from headers, query or body. |
| Authorisation as dependencies | FastAPI dependencies return the authorised entity. Deleting a document requires the **owner or an admin**. Reprocessing requires an **admin**. Hiding a button in the UI is a convenience; the API still returns `403`. |
| Scope note | v1 serves **one organisation**. There is no multi-tenancy, and every authenticated user can read every non-deleted document. This is a documented design assumption, not an oversight. See [limitations](#roadmap-and-known-limitations). |

### Upload and file safety

| Control | Implementation |
|---|---|
| Ordered validation | Filename sanitisation, then extension, then declared MIME type, then **streamed** size check, then non-empty check, then **magic bytes** (`%PDF-` / `PK\x03\x04`). The first failure stops processing, and nothing durable is written. |
| Size limit enforced while streaming | Bytes are counted during the upload, and the request is aborted at `MAX_UPLOAD_BYTES` (25 MiB). The file is never fully buffered first. |
| Zip-bomb defence (DOCX) | Before any archive entry is read, the ZIP central directory is checked for entry count (≤ 2,000), total uncompressed size (≤ 200 MiB) and compression ratio (≤ 200:1). |
| XXE | DOCX XML is parsed by python-docx's `lxml` parser with `resolve_entities=False`. Tests include an XXE-bearing DOCX. |
| No path traversal by construction | Filenames are sanitised and used for display only. Storage keys are generated on the server (`{yyyy}/{mm}/{uuid4}{ext}`). |
| Duplicate detection | A SHA-256 content hash plus a unique partial index. A duplicate upload gets `409 DUPLICATE_DOCUMENT`, including under concurrent uploads. |
| No file serving | Original files are never served back to the browser, so there is no stored-XSS or content-sniffing risk. |
| Rejected uploads are audited | Rejected uploads are recorded as security audit events. |

### Prompt-injection and grounding guardrails

| Layer | Implementation |
|---|---|
| Structural isolation | Chunk text is XML-escaped inside `<chunk>` elements, and metadata goes in escaped attributes. A document can't close its own element or forge attributes. Document text never goes into a `system` message. |
| Instructional | The system prompt names the attack and tells the model in advance to ignore instructions found in documents. The question comes last. |
| Capability | The model has no tools, no function calling, no database and no network access. Its only output is one JSON object matching `GroundedAnswerModel`. |
| Schema | OpenAI structured outputs, validated again with Pydantic v2 before use. Claims must cite chunk IDs the model was actually given. |
| Citation validation | Each citation must name a chunk in the assembled context (set membership), and its quoted span must appear verbatim in the stored chunk text. Unknown IDs are dropped. If none survive, the answer becomes a refusal. |
| Gate isolation | The answer-or-refuse decision is arithmetic on similarity scores and never sees the question or document text, so **injected text can't talk the system into answering**. A DB check constraint (`ck_answers_confidence_gate`) enforces the same rule a second time. |
| Fabrication canary | Prometheus alert `FabricationCanary` fires when more than 2% of answers drop a citation for an unknown chunk ID. |
| Tested adversarially | The injection corpus covers direct override, role reassignment, fake system framing, requests to cite a specific chunk, prompt-exfiltration attempts, zero-width and homoglyph obfuscation, and instructions split across two chunks. |

> **Residual risk, stated honestly:** these layers stop injected text from changing system
> behaviour, faking citations, changing state or exfiltrating data. They **cannot** guarantee the
> model won't write a misleading *summary* of a document that really does contain the injected
> text. The product answer to that is that every citation opens the verbatim source.

### Abuse, rate limiting and idempotency

| Control | Implementation |
|---|---|
| Rate limits | Login: 10 requests/min per IP. Uploads: 30/hour, answers: 60/hour, search: 300/hour, all per user. A `429` includes `Retry-After` and never shows anyone else's usage. |
| Cheap refusals | The refusal path makes no LLM call, so a flood of nonsense questions costs no tokens. |
| Idempotency keys | `POST /api/v1/documents` accepts an optional `Idempotency-Key` (UUID). Keys are stored in Postgres (`idempotency_keys`, 24h TTL) and replays return `Idempotency-Replayed: true`. |
| Input validation | Pydantic v2 validates every request. `422` responses describe the *shape* of the problem and never echo the offending value. Malformed UUIDs fail before any database access. |
| SQL safety | Every query is parameterised. `websearch_to_tsquery` receives user input as a bound parameter. |

### Secrets, logging and audit

| Control | Implementation |
|---|---|
| Secrets from the environment only | No secret has a default value in code. Secret settings use `pydantic.SecretStr`, so their `repr` is redacted. `<VAR>_FILE` takes precedence over `<VAR>` for Docker secrets. |
| Refuses to start when misconfigured | Startup fails if `JWT_SECRET_KEY` is under 32 characters or looks like a placeholder. In production it also fails if API docs are enabled, `FORCE_HTTPS` is off, `CORS_ALLOWED_ORIGINS` contains `*`, or storage isn't S3. `make secrets-check` fails if any `REPLACE_ME`/`CHANGE_ME` value is left in `.env`. |
| Browser never sees provider keys | `OPENAI_API_KEY` exists only in the backend process. Only four non-sensitive `NEXT_PUBLIC_*` values (API origin, upload limit, app version, demo flag) reach the browser. |
| Log redaction | JSON structured logs. A redaction filter removes `sk-…`, `Bearer …` and `eyJ…` (JWT) patterns as a backstop. **Document text, chunk content, prompts and question text are never logged.** Logs are correlated by IDs, scores and `X-Request-ID`. |
| Audit events | Upload, indexed, failed, delete, reprocess, answer created or refused, rejected upload, and login success or failure are recorded with actor, action, target and request ID, in the same transaction as the action. |
| Secret scanning | A `detect-secrets` pre-commit hook, also run on every PR in CI. |
| Dependency auditing | `pip-audit` and `npm audit --audit-level=high` run in CI. `uv.lock` and `package-lock.json` pin dependencies. |
| Hardened containers | Non-root users, read-only root filesystems, `cap_drop: ALL`, `no-new-privileges`, and `tmpfs` for `/tmp`. The production overlay publishes no DB or API ports, and TLS terminates at a Caddy reverse proxy. |
| Metrics endpoint | `GET /metrics` can require `METRICS_TOKEN`, compared in constant time. |

---

## Reliability and fallbacks

| Concern | Behaviour |
|---|---|
| **LLM output fails the schema** | One structural repair attempt, then a clean `502 LLM_INVALID_OUTPUT`. The API never returns a partial or free-text answer. |
| **LLM timeout** | Each provider call has a timeout (`LLM_TIMEOUT_SECONDS`, 45 s). When retries are used up, the API returns `504 LLM_TIMEOUT`. |
| **Transient provider errors** | The OpenAI SDK's own retries are turned off and replaced with an explicit policy: retry only on `429/500/502/503/504` and connection errors, with exponential backoff (1 s → 4 s for the LLM, 1 s → 4 s → 16 s for embeddings) and ±20% jitter. `400`/`401` are never retried. |
| **Conflicting evidence** | Near-tied passages from different documents trigger a conflict notice and **escalate that single call** to `LLM_CONFLICT_ESCALATION_MODEL` (default `gpt-4o`). |
| **Provider outage** | Errors are typed (`503`/`502`/`504`) and never turn into unsourced answers. Readiness checks deliberately **don't** depend on OpenAI, so listing, citation resolution and history keep working during an outage. |
| **Ingestion failures** | Job-level retries with backoff (up to 3 attempts), then a terminal `failed` status with a readable failure code (`EXTRACTION_NO_TEXT_LAYER`, `EXTRACTION_ENCRYPTED_DOCUMENT`, `EMBEDDING_PROVIDER_ERROR`, …). An admin can reprocess failed documents. Reprocessing swaps chunk generations atomically. |
| **Worker crashes** | Jobs are claimed with `SELECT … FOR UPDATE SKIP LOCKED`. A job stuck in `running` for more than 30 minutes is reclaimed and requeued, or failed once its attempts run out, so it can't loop forever. Restarting the API is safe at any time. |
| **Race conditions** | Documents deleted between retrieval and answer assembly are dropped and confidence is recalculated. Concurrent identical uploads resolve to a single document through the unique index. |
| **Database** | Pool timeouts and a server-side statement timeout (15 s). |
| **Health checks** | `/health/live` is a liveness probe. `/health/ready` checks DB connectivity, the `vector` extension, migrations being current, embedding dimension and model matching the stored vectors, and the HNSW index. The API **won't start** if any of these fail. Docker `HEALTHCHECK`s and Compose `depends_on: service_healthy` gate startup order. |
| **Graceful shutdown** | Background loops (ingestion worker, stuck-job reclaim, retention sweep) get a grace period to finish their current iteration. No transaction is held open across a sleep. |
| **Observability** | JSON logs with `request_id`, `job_id` and W3C `traceparent` trace and span IDs. Prometheus metrics cover retrieval latency, top similarity, empty results, confidence, answers by decision, citations dropped, LLM calls, latency, tokens and repairs, and embedding calls and tokens. Includes a ready-to-load alert rule (`observability/prometheus/alerts.yml`). |

---

## Architecture

```mermaid
flowchart LR
    subgraph Browser["Browser (untrusted)"]
        UI["Next.js 15 App Router<br/>React 19 · TypeScript · Tailwind 4"]
    end

    subgraph Web["web container"]
        RH["Route handlers<br/>/api/auth/login · logout · session<br/>(httpOnly cookie)"]
        MW["Middleware<br/>nonce CSP + auth redirect"]
    end

    subgraph API["api container (FastAPI)"]
        direction TB
        EDGE["Request-ID · security headers · CORS<br/>JWT dependency · rate limiter"]
        SVC["Services<br/>documents · ingestion · retrieval<br/>answers · citations · audit · idempotency"]
        CORE["Deterministic core<br/>RRF fusion · confidence gate<br/>context assembly · citation validator"]
        WK["In-process workers<br/>ingestion · stuck-job reclaim · retention"]
    end

    subgraph Data["Data"]
        PG[("PostgreSQL 16 + pgvector<br/>HNSW + GIN indexes")]
        OBJ[("S3-compatible storage<br/>MinIO locally")]
    end

    OAI["OpenAI<br/>Embeddings + Chat Completions"]

    UI -->|HTTPS JSON / multipart| EDGE
    UI --> RH
    RH -->|server-to-server login| EDGE
    EDGE --> SVC --> CORE
    SVC --> PG
    SVC --> OBJ
    WK --> PG
    WK --> OBJ
    SVC -->|egress only| OAI
    WK -->|egress only| OAI
```

**Design principles**

- **Deterministic core, probabilistic edge.** State transitions, authorisation, validation,
  scoring and the answer/refuse decision are deterministic Python and SQL. The LLM has one job:
  turning passages that were already selected into prose. It can't change state.
- **Evidence is authoritative; the model is not.** Retrieved chunks are the source of truth for
  facts.
- **Contracts before code.** Pydantic v2 is the single source of the schema: from it the OpenAPI
  document is generated, and from that the TypeScript types and Zod schemas.
- **The database enforces what it can.** Foreign keys, unique and partial indexes, check
  constraints (including the confidence gate) and generated `tsvector` columns.
- **Enforced layering.** `import-linter` contracts enforce
  `cli → api|worker → services → rag → retrieval → db|providers|ingestion|storage → llm → schemas|observability`,
  and **only `app.providers` may import the OpenAI SDK.** Embedding and LLM clients sit behind
  `Protocol` interfaces, so the provider can be swapped.
- **Asynchronous ingestion, synchronous querying.** Upload returns `202 Accepted` with a tracked
  job. Questions are answered within the request.

The main technical decisions are recorded in 27 Architecture Decision Records: PostgreSQL +
pgvector as the single datastore, HNSW with cosine distance, RRF hybrid retrieval, strict
structured outputs, a pre-LLM confidence gate, database-backed in-process jobs, immutable chunk
generations, citations as rows with `RESTRICT` foreign keys, no OCR in v1, in-process rate
limiting behind an interface, retention windows, and calibration of the confidence threshold and
chunk size from measured data.

---

## Tech stack

| Layer | Technology |
|---|---|
| Backend API | Python 3.12, FastAPI, Uvicorn, Pydantic v2 + pydantic-settings |
| Persistence | PostgreSQL 16, pgvector (HNSW, cosine), SQLAlchemy 2.0 (async, psycopg 3), Alembic |
| Ingestion | pypdf, pdfplumber, python-docx, LlamaIndex core (chunking utilities), tiktoken |
| AI providers | OpenAI `text-embedding-3-small` (1536-d) · `gpt-4o-mini` (answers) · `gpt-4o` (conflict escalation) |
| Auth and security | PyJWT (HS256), argon2-cffi (Argon2id), detect-secrets, pip-audit, npm audit |
| Object storage | S3-compatible via boto3 (MinIO in development, managed S3 in production) or local filesystem |
| Observability | Structured JSON logging, prometheus-client, Prometheus alert rules |
| Frontend | Next.js 15 (App Router), React 19, TypeScript 5, Tailwind CSS 4, TanStack Query 5, React Hook Form, Zod |
| API contract | openapi-typescript, openapi-zod-client (generated from the FastAPI OpenAPI schema) |
| Testing | pytest, pytest-asyncio, Testcontainers (Postgres), httpx, Vitest, Testing Library, MSW, jest-axe, Playwright |
| Tooling | uv, ruff, mypy (`--strict`), import-linter, ESLint, Prettier, pre-commit |
| Infrastructure | Docker (multi-stage), Docker Compose (dev + production overlay), Caddy (TLS), GitHub Actions |

---

## Quick start

> [!IMPORTANT]
> The source is being published incrementally (see the note at the top). The commands below are
> for the complete repository and will work end to end once the full codebase is available.

### Prerequisites

- **Docker** with Docker Compose v2
- **An OpenAI API key** (used for embeddings and answers, so it costs real money)
- `make` (optional, for the shortcuts below)
- Free host ports `3000`, `8000`, `5432`, `9000`, `9001`. Each can be changed in `.env` with
  `WEB_HOST_PORT`, `API_HOST_PORT`, `DB_HOST_PORT`, `STORAGE_API_HOST_PORT` and
  `STORAGE_CONSOLE_HOST_PORT`.

### 1. Clone and configure

```bash
git clone https://github.com/MujtabaAhmad21/AI-Enterprise-Document-Intelligence-System.git
cd AI-Enterprise-Document-Intelligence-System

cp .env.example .env
```

Open `.env` and replace **every** `REPLACE_ME` value:

- `OPENAI_API_KEY`: your OpenAI key.
- `JWT_SECRET_KEY`: at least 32 random characters, for example the output of `openssl rand -hex 32`.
- `POSTGRES_PASSWORD`: use the same value inside `DATABASE_URL`.
- `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`: local MinIO credentials. Set
  `STORAGE_S3_ACCESS_KEY` / `STORAGE_S3_SECRET_KEY` to the **same** two values.
- `SEED_ADMIN_PASSWORD` / `SEED_MEMBER_PASSWORD`: passwords for the development users.

Then confirm no placeholder is left:

```bash
make secrets-check
```

If you want the optional sample corpus in step 3, generate it now. The sample documents are
synthetic and not committed. The generator uses only the standard library and needs no install:

```bash
python3 tests/fixtures/generate.py
```

### 2. Start the stack

```bash
docker compose up --build -d      # or: make up   (runs in the foreground)
```

Compose starts PostgreSQL + pgvector and MinIO and waits for them to be healthy. It then runs
**`alembic upgrade head`** as a one-shot `migrate` service, creates a private storage bucket, and
starts the API and web app. The first build downloads a lot; if it hits a network timeout, run it
again (finished layers are cached).

### 3. Seed users (and optionally a sample corpus)

```bash
# admin@example.com and member@example.com, passwords taken from .env (refuses in production)
docker compose exec api python -m app.cli seed-users

# Optional: ingest three sample documents through the real pipeline (real embedding calls)
docker compose exec api python -m app.cli seed-corpus
```

### 4. Open it

| URL | What |
|---|---|
| http://localhost:3000 | Web app (sign in with a seeded user) |
| http://localhost:8000/health/ready | Readiness report |
| http://localhost:8000/docs | Interactive API docs (development only, disabled in production) |
| http://localhost:8000/metrics | Prometheus metrics |
| http://localhost:9001 | MinIO console |

### Makefile targets

| Target | Does |
|---|---|
| `make up` / `make down` | `docker compose up --build` / `docker compose down` |
| `make reset` | **Destroys all data** (DB and document volumes) after typing `yes`, then rebuilds |
| `make migrate` | Runs the `migrate` service (`alembic upgrade head`) |
| `make revision m="message"` | Autogenerates a new Alembic revision |
| `make openapi` / `make types` | Exports `openapi.json` and regenerates frontend types (the contract-sync pair) |
| `make logs` | Follows API logs |
| `make psql` | Opens `psql` in the database container |
| `make secrets-check` | Fails if any placeholder value is still in `.env` |

> The runtime API image is built without dev dependencies. Run the test and lint suites on the
> host with `uv`, as shown in [Testing and quality gates](#testing-and-quality-gates).

**Development tips:** `web` is a production Next.js build, so rebuild it after frontend edits
with `docker compose up -d --build web`. `api` bind-mounts `backend/app` read-only, so
`docker compose restart api` picks up backend edits.

---

## Production deployment

The production overlay (`docker-compose.prod.yml`) is applied on top of the base file:

```bash
# 1. Secrets as files, never committed (secrets/ is git-ignored)
mkdir -p secrets
printf '%s' "<your-openai-key>"       > secrets/openai_api_key
printf '%s' "<32+ random characters>" > secrets/jwt_secret_key
printf '%s' "<db password>"           > secrets/postgres_password

# 2. Images built and pushed by CI, deployed by tag/digest (not rebuilt on the host)
export API_IMAGE=registry.example.com/didoc-api:sha-abc123
export WEB_IMAGE=registry.example.com/didoc-web:sha-abc123

# 3. Up
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

What the overlay changes:

- `OPENAI_API_KEY`, `JWT_SECRET_KEY` and `POSTGRES_PASSWORD` become **Docker secrets** mounted
  read-only at `/run/secrets/*` and read through `<VAR>_FILE`. The `.env` file is **not** used by
  the containers, so supply the remaining non-secret settings (such as `CORS_ALLOWED_ORIGINS` and
  `STORAGE_S3_*`) through your platform's environment.
- `ENVIRONMENT=production`, and API docs are off. The app **refuses to start** unless HTTPS is
  enforced, CORS has no wildcard, and storage is S3.
- DB, API and web ports are no longer published. A **Caddy** reverse proxy on `80/443` terminates
  TLS, using your `docker/Caddyfile` and certificates.
- MinIO is removed. Point `STORAGE_S3_*` at managed S3-compatible storage.
- Restart policies and CPU/memory limits are added for every service.
- **Before your first deploy:** replace the `@sha256:REPLACE_WITH_PINNED_DIGEST` placeholders for
  `pgvector/pgvector:pg16` and `caddy` with real digests
  (`docker inspect --format='{{index .RepoDigests 0}}' <image>`).

**Backups:** take a nightly `pg_dump -Fc` (it includes the embeddings) plus object-storage
backups on the same schedule. After a restore, rebuild the HNSW index rather than restoring it.

---

## Local development without Docker

This mirrors how the CI end-to-end job runs the stack. You need Python 3.12, [uv](https://docs.astral.sh/uv/),
Node.js 22, and a PostgreSQL 16 with the `vector` extension (the `pgvector/pgvector:pg16` image
is the easiest option).

```bash
# Backend
cd backend
uv sync --dev
cat > .env <<'EOF'
ENVIRONMENT=development
CORS_ALLOWED_ORIGINS=http://localhost:3000
POSTGRES_USER=didoc
POSTGRES_PASSWORD=REPLACE_ME_DB_PASSWORD
POSTGRES_DB=didoc
DATABASE_URL=postgresql+psycopg://didoc:REPLACE_ME_DB_PASSWORD@localhost:5432/didoc
OPENAI_API_KEY=sk-REPLACE_ME
JWT_SECRET_KEY=REPLACE_ME_WITH_32_PLUS_RANDOM_BYTES
SEED_ADMIN_PASSWORD=REPLACE_ME_ADMIN_PASSWORD
SEED_MEMBER_PASSWORD=REPLACE_ME_MEMBER_PASSWORD
STORAGE_BACKEND=local
STORAGE_LOCAL_ROOT=/tmp/didoc-storage
EMBEDDING_DIM=1536
EOF
# ...replace the REPLACE_ME values, then:
uv run --env-file .env alembic upgrade head
uv run --env-file .env python -m app.cli seed-users
uv run --env-file .env uvicorn app.main:app --reload --port 8000

# Frontend (second terminal)
cd frontend
npm ci
printf 'NEXT_PUBLIC_API_BASE_URL=http://localhost:8000\nNEXT_PUBLIC_MAX_UPLOAD_BYTES=26214400\n' > .env.local
npm run dev    # http://localhost:3000
```

The settings object doesn't read `.env` files by itself, so always pass `--env-file`.

**Public demo build:** `frontend/scripts/make-vercel-demo.sh` produces a `vercel-demo/` copy of
the frontend. It has `NEXT_PUBLIC_DEMO_MODE=true` baked in and leaves out `node_modules`, build
output and every `.env*` file, ready for Vercel.

---

## Configuration reference

All configuration comes from environment variables. It is validated once at startup, and the
process exits with named errors if anything is invalid. `.env.example` lists the core set. Every
value shown there is a placeholder.

| Variable | `.env.example` / default | Purpose |
|---|---|---|
| `ENVIRONMENT` | `development` | `development` \| `test` \| `staging` \| `production` (production turns on the strict startup checks) |
| `LOG_LEVEL` | `INFO` | Log level |
| `CORS_ALLOWED_ORIGINS` | `http://localhost:3000` | Comma-separated origin allowlist (no `*` in production) |
| `POSTGRES_USER` / `POSTGRES_DB` | `didoc` | Database role and name |
| `POSTGRES_PASSWORD` | `REPLACE_ME_DB_PASSWORD` | Database password (**secret**) |
| `DATABASE_URL` | `postgresql+psycopg://didoc:REPLACE_ME_DB_PASSWORD@db:5432/didoc` | SQLAlchemy URL (**secret**) |
| `OPENAI_API_KEY` | `sk-REPLACE_ME` | OpenAI key, backend only (**secret**) |
| `EMBEDDING_MODEL` / `EMBEDDING_DIM` | `text-embedding-3-small` / `1536` | Must match the stored vectors; readiness fails otherwise |
| `LLM_MODEL` | `gpt-4o-mini` | Answer model |
| `LLM_CONFLICT_ESCALATION_MODEL` | `gpt-4o` (default) | Model used for near-tied, cross-document conflicts |
| `RETRIEVAL_TOP_K` | `8` | Chunks kept after fusion |
| `RETRIEVAL_MIN_COSINE` | `0.30` | Similarity floor for a chunk to count toward coverage |
| `ANSWER_CONFIDENCE_THRESHOLD` | `0.50` | Refusal gate threshold, calibrated from measured data |
| `JWT_SECRET_KEY` | `REPLACE_ME_WITH_32_PLUS_RANDOM_BYTES` | JWT signing key, at least 32 characters (**secret**) |
| `SEED_ADMIN_PASSWORD` / `SEED_MEMBER_PASSWORD` | `REPLACE_ME_…` | Dev/staging seed users only (**secret**) |
| `STORAGE_BACKEND` | `s3` | `s3` or `local` (production requires `s3`) |
| `STORAGE_S3_ENDPOINT` / `STORAGE_S3_BUCKET` | `http://storage:9000` / `didoc-documents` | S3-compatible storage |
| `STORAGE_S3_ACCESS_KEY` / `STORAGE_S3_SECRET_KEY` | `REPLACE_ME_…` | Storage credentials (**secret**) |
| `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` | `REPLACE_ME_…` | Local MinIO only (**secret**) |
| `DOCUMENT_FILE_RETENTION_DAYS` | `90` | Purge original files this long after soft delete |
| `QUESTION_RETENTION_DAYS` | `365` | Redact question text after this long |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | API origin **as the browser sees it** (public) |
| `NEXT_PUBLIC_MAX_UPLOAD_BYTES` | `26214400` | Client-side upload limit (public) |

<details>
<summary><strong>Optional tuning (code defaults)</strong></summary>

| Variable | Default | Purpose |
|---|---|---|
| `LLM_TIMEOUT_SECONDS` / `LLM_MAX_RETRIES` | `45` / `2` | LLM call timeout and transport retries |
| `LLM_MAX_CONTEXT_TOKENS` / `LLM_MAX_OUTPUT_TOKENS` | `6000` / `1200` | Context and output token budgets (checked against the model's context window at startup) |
| `EMBEDDING_BATCH_SIZE` / `EMBEDDING_TIMEOUT_SECONDS` / `EMBEDDING_MAX_RETRIES` | `64` / `20` / `3` | Embedding batching and retry |
| `MAX_UPLOAD_BYTES` / `MAX_DOCUMENT_PAGES` | `26214400` / `1500` | Upload limits |
| `CHUNK_TARGET_TOKENS` / `CHUNK_OVERLAP_TOKENS` / `CHUNK_MAX_TOKENS` | `512` / `64` / `768` | Chunking |
| `ZIP_MAX_ENTRIES` / `ZIP_MAX_UNCOMPRESSED_BYTES` / `ZIP_MAX_RATIO` | `2000` / `209715200` / `200` | DOCX zip-bomb limits |
| `JWT_EXPIRE_MINUTES` | `60` | Access-token lifetime |
| `AUTH_RATE_LIMIT_PER_MINUTE` | `10` | Login attempts per IP |
| `UPLOAD_` / `ANSWER_` / `SEARCH_RATE_LIMIT_PER_HOUR` | `30` / `60` / `300` | Per-user limits |
| `INGESTION_MAX_ATTEMPTS` / `INGESTION_STUCK_AFTER_SECONDS` | `3` / `1800` | Job retry and stuck-job reclaim |
| `DB_STATEMENT_TIMEOUT_SECONDS` | `15` | Server-side statement timeout |
| `APP_ROLE` | `all` | `api` \| `worker` \| `all`; `api` runs no background loops |
| `ENABLE_API_DOCS` / `FORCE_HTTPS` | derived from `ENVIRONMENT` | Must be `false` / `true` in production |
| `METRICS_TOKEN` | unset | If set, `/metrics` requires `Authorization: Bearer <token>` |
| `RETENTION_ENABLED` | `true` | Turns the daily retention sweep on or off |
| `STORAGE_LOCAL_ROOT` | `/var/lib/didoc/storage` | Root directory for `STORAGE_BACKEND=local` |
| `API_INTERNAL_URL` | unset | Server-only address the web container uses to reach the API (Compose sets `http://api:8000`) |
| `NEXT_PUBLIC_DEMO_MODE` | unset | `true` builds the backend-less public demo |

</details>

---

## API overview

All `/api/v1/*` routes need a bearer token except `POST /api/v1/auth/token`. Errors use a single
`ErrorResponse` envelope with a machine-readable `error.code`. Every response carries
`X-Request-ID`.

| Method and path | Purpose |
|---|---|
| `POST /api/v1/auth/token` | Exchange email and password for a JWT (rate-limited per IP) |
| `GET /api/v1/users/me` | Current user |
| `POST /api/v1/documents` | Upload a PDF or DOCX → `202 Accepted` (optional `Idempotency-Key`) |
| `GET /api/v1/documents` | List with keyset pagination and filters (`status`, filename, uploader) |
| `GET /api/v1/documents/{id}` | Detail: chunk, page and token counts, ingestion timings |
| `GET /api/v1/documents/{id}/status` | Ingestion state, progress counters, failure detail |
| `GET /api/v1/documents/{id}/chunks` | Chunks of the current generation |
| `DELETE /api/v1/documents/{id}` | Soft delete (owner or admin) → `204` |
| `POST /api/v1/documents/{id}/reprocess` | Re-ingest (admin only) |
| `POST /api/v1/search` | Hybrid passage search with all component scores (no LLM) |
| `POST /api/v1/answers` | Ask a grounded question → `answered` with citations, or `insufficient_context` |
| `GET /api/v1/answers` · `GET /api/v1/answers/{id}` | Answer history · immutable answer record |
| `GET /api/v1/chunks/{chunk_id}` | Verbatim source for a citation |
| `POST /api/v1/citations/resolve` | Resolve several citations at once |
| `GET /health/live` · `GET /health/ready` | Liveness · readiness |
| `GET /metrics` | Prometheus exposition (optionally token-protected) |

---

## Testing and quality gates

```bash
# Backend: needs Docker running (integration tests use Testcontainers PostgreSQL + pgvector)
cd backend
uv sync --dev
uv run pytest                     # default suite (unit, contract, integration, security, failure, api)
uv run ruff check .
uv run mypy app migrations        # strict mode
uv run lint-imports               # architecture layering contracts
uv run pip-audit

# Frontend
cd frontend
npm ci
npm run lint && npm run typecheck && npm test && npm run build

# End-to-end (Playwright, against a running stack)
cd e2e && npm ci && npx playwright test
```

Suites that call the **real** OpenAI API are excluded from the default run by pytest markers and
must be run on purpose: `-m grounding` (grounding and refusal suites), `-m calibration`
(chunk-size sweep), `-m nightly` (live provider smoke test), and `-m perf` (scale and latency
benchmark).

**CI (GitHub Actions)** runs these gates on every push and PR:

| Job | Gate |
|---|---|
| Static (backend) | ruff · mypy `--strict` · import-linter · pip-audit · single Alembic head |
| Static (frontend) | ESLint · `tsc --noEmit` · `npm audit --audit-level=high` |
| Frontend test + build | Vitest (incl. jest-axe accessibility checks) · `next build` |
| Contract drift | Regenerates OpenAPI → TypeScript/Zod and fails on any diff |
| Unit · Contract · Security · Failure injection | Separate pytest jobs |
| Integration + coverage | Real PostgreSQL + pgvector via Testcontainers. **≥ 85% line coverage** on `app/services`, and **100% branch coverage** on the confidence gate, citation validator and RRF fusion |
| Pre-commit | detect-secrets scan over all files |
| Docker clean clone | `cp .env.example .env` → `make secrets-check` → `docker compose up --build` → API and web healthy within 3 minutes |
| E2E (push to `main`) | Playwright user journeys against the full stack |
| Nightly | Live LLM provider contract smoke test (reported, never blocks PRs) |

Other test categories: every OpenAPI route must be covered by at least one tagged test. The
failure-injection suite covers DB outage, LLM timeout, concurrent uploads and reprocesses, a
document deleted mid-answer, readiness degradation, and malicious-upload auditing. The
documentation examples are run as tests.

---

## Measured results

Only numbers that were measured and recorded during development are listed here. Targets that
were missed are included.

| Measure | Result | Target |
|---|---|---|
| Ingestion latency (120-page PDF, 113 chunks, real pipeline) | **12.8 s** | ≤ 120 s p95 ✅ |
| Search latency at 50,000 chunks (50 real queries) | p50 956 ms / **p95 1,487 ms** | ≤ 800 ms p95 ❌ (see limitations) |
| Retrieval recall@8, chunk-size sweep on the fixture corpus | **0.978** (45/46) at every tested size | Informs the 512/64 default |
| Line coverage, `app/services` | **93.19%** | ≥ 85% ✅ |
| Branch coverage, confidence gate + citation validator + fusion | **100%** | 100% ✅ |
| Backend tests in the default run | 381 | none |
| Frontend Vitest tests | 77 | none |

---

## Project structure

```text
.
├── backend/
│   ├── app/
│   │   ├── api/            # FastAPI routers + exception handlers (HTTP shape only)
│   │   ├── auth/           # JWT, Argon2id passwords, auth dependencies
│   │   ├── middleware/     # request ID, security headers, rate limiting
│   │   ├── services/       # documents, ingestion, retrieval, answers, citations, audit, idempotency, upload validation
│   │   ├── rag/            # context assembly, citation validator, span matching, rendering
│   │   ├── retrieval/      # vector, keyword, RRF fusion, confidence gate
│   │   ├── ingestion/      # PDF/DOCX extractors, normaliser, chunker
│   │   ├── providers/      # OpenAI embedding + LLM clients (the only OpenAI SDK importers)
│   │   ├── llm/            # system prompt
│   │   ├── storage/        # S3 + local storage adapters
│   │   ├── worker/         # ingestion loop, stuck-job reclaim, retention sweep
│   │   ├── db/             # SQLAlchemy models, session, readiness checks
│   │   ├── schemas/        # Pydantic v2 wire contracts
│   │   ├── observability/  # Prometheus metrics
│   │   ├── cli.py          # export-openapi · seed-users · seed-corpus
│   │   ├── config.py       # validated settings + startup assertions
│   │   ├── logging.py      # JSON logs + secret redaction
│   │   └── main.py         # ASGI app, middleware, lifespan (readiness + background loops)
│   ├── migrations/         # Alembic revisions 0001–0009 (hand-reviewed DDL)
│   ├── tests/              # unit, contract, integration, security, failure, api, grounding, calibration, perf, nightly
│   ├── .importlinter       # layering contracts
│   ├── Dockerfile
│   └── pyproject.toml / uv.lock
├── frontend/
│   ├── app/                # App Router: (auth)/login, (app)/documents|ask|search|answers, api/auth/*
│   ├── components/         # documents, qa (answers, citations, refusals), search, ui
│   ├── lib/                # API client, generated types/schemas, auth, hooks, demo mode
│   ├── middleware.ts       # nonce CSP + auth redirect
│   ├── scripts/            # type generation, Vercel demo build
│   └── Dockerfile
├── e2e/                    # Playwright journeys + seeding
├── tests/fixtures/         # deterministic generator for the synthetic test corpus (incl. injection, conflict, XXE, zip-bomb fixtures)
├── observability/prometheus/alerts.yml
├── docker/Caddyfile        # production TLS proxy config
├── docker-compose.yml      # development stack
├── docker-compose.prod.yml # production overlay
├── .github/workflows/      # ci.yml, nightly.yml
├── Makefile
└── .env.example
```

---

## Roadmap and known limitations

These are the limits as they stand today.

**Scope limits in v1 (by design)**

- **One organisation per deployment.** There is no multi-tenancy or per-document access control.
  Every authenticated user can read every non-deleted document. Deployments where documents must
  be confidential *between* users need per-document ACLs first.
- **PDF and DOCX only. No OCR:** scanned PDFs are detected and fail with a clear reason.
  Full-text search is configured for **English**.
- **No streaming and no chat memory.** Each question is answered on its own, and the whole answer
  is validated before it is shown.
- **Document text is sent to OpenAI.** All chunks and queries go to the embeddings API, and the
  question plus the top passages go to the chat model. No zero-data-retention setup is
  configured. For highly confidential corpora, consider OpenAI ZDR, Azure OpenAI, or a
  self-hosted model behind the existing provider interfaces.
- **One API replica.** The rate limiter keeps its counters in the process. Running a second
  replica needs the Redis-backed `RateLimiter` adapter first.

**Known gaps**

- **Search p95 at 50k chunks is 1.49 s against an 800 ms target.** The cause was traced to
  latency variance in the query-embedding call, not to the retrieval SQL. It is recorded in an
  ADR and not fixed yet. The full 100k-chunk benchmark hasn't been run.
- **Refusal coverage:** with the threshold calibrated at `0.50`, the curated "unanswerable" set
  doesn't reach 100% refusal on the fixture corpus. The cause is repeated filler text inflating
  the coverage term. Three grounding tests are kept as honest `xfail`s.
- **The audit log is append-only by application discipline.** The migration that revokes
  `UPDATE/DELETE` has no effect while the app connects as the table owner. Enforcing it needs a
  separate least-privilege DB role.
- **Conflict escalation** has no regression test against the live model yet (the existing test
  uses a fake LLM), and its false-positive rate hasn't been measured.
- **Production TLS through Caddy hasn't been tested end to end**, and base-image digests in the
  production overlay are placeholders you must pin.
- Only one Prometheus alert (`FabricationCanary`) is wired so far. More alert rules and an
  embedding-migration (`reembed-all`) command are planned.
- The Makefile's `test`/`test-cov`/`lint` targets run inside the runtime image, which has no dev
  dependencies. Run these suites on the host with `uv` instead.

---

## Contributing

Issues and pull requests are welcome once the full source is published. Please:

1. Open an issue first for anything beyond a small fix.
2. Run `pre-commit install` once per clone (secret scanning runs on every commit).
3. Keep the gates green: `ruff`, `mypy --strict`, `lint-imports`, `pytest`, ESLint, `tsc`,
   Vitest, and the OpenAPI → TypeScript drift check (`make openapi && make types`).
4. Never commit real secrets. `.env`, `secrets/` and generated demo builds are git-ignored.

---

## License

No license has been published for this repository yet. Please open an issue if you want to use
the code.

---

## Author

**Mujtaba Ahmad**, [@MujtabaAhmad21](https://github.com/MujtabaAhmad21)

If this project is useful to you, consider giving it a ⭐.
