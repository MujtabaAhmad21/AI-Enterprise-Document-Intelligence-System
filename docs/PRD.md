# PRD.md — Product Requirements Document

**Project:** AI Enterprise Document Intelligence System (Project 3)
**Architecture classification:** Tier 3 — Grounded Retrieval-Augmented Generation (RAG)
**Status:** Specification (pre-implementation)
**Authority:** This document is authoritative for *problem definition, scope, functional requirements (FR-*), non-functional requirements (NFR-*), business rules (BR-*), and success criteria*. See [README.md](README.md#source-of-truth) for the full precedence hierarchy.

---

## 1. Problem Statement

Enterprises accumulate hundreds to thousands of unstructured documents — compliance PDFs, contracts, technical manuals, policy handbooks. Answering a single factual question ("What is the notice period for termination in the Acme MSA?") today requires a human to locate the right document, skim it, and manually verify the passage.

Two failure modes dominate existing attempts to automate this:

1. **Keyword search alone** returns documents, not answers, and misses semantically equivalent phrasing.
2. **Ungrounded LLM assistants** produce fluent answers that are unverifiable and sometimes fabricated. In compliance and contract contexts, an unverifiable answer is worse than no answer, because it carries false authority.

The system MUST therefore answer questions **only** from retrieved document evidence, MUST attach a machine-verifiable citation to every factual claim, and MUST deterministically refuse when retrieved evidence is insufficient.

---

## 2. Goals

| ID | Goal | Measured by |
|----|------|-------------|
| G-1 | Turn an uploaded PDF/DOCX corpus into a queryable, cited knowledge base | End-to-end ingestion → answer works for the acceptance corpus |
| G-2 | Every factual claim in an answer is traceable to an exact chunk | `INV-001`, `INV-002` hold in all tests ([TESTING_STRATEGY.md](TESTING_STRATEGY.md)) |
| G-3 | The system refuses rather than hallucinates when evidence is weak | `INV-004` — refusal is decided by backend arithmetic, not by the LLM |
| G-4 | Zero contract drift between FastAPI, Pydantic, PostgreSQL and Next.js | [TYPESCRIPT_CONTRACT.md](TYPESCRIPT_CONTRACT.md) contract tests pass |
| G-5 | A reviewer can audit *why* any answer was produced | Retrieval scores, chunk IDs, model, and token usage persisted per answer |
| G-6 | Reproducible local + containerised environment | `docker compose up` yields a working system from a clean clone |

## 3. Non-Goals (explicitly out of scope for v1)

| ID | Non-goal | Rationale |
|----|----------|-----------|
| NG-1 | Multi-tenant organisations / workspace isolation | Belongs to Project 5 (Tier 5 capstone) |
| NG-2 | Agentic tool-calling, autonomous workflows, MCP exposure | Belongs to Projects 4 and 5 |
| NG-3 | Document *editing*, versioning as a first-class user feature, or collaborative annotation | Not in the defined functional scope |
| NG-4 | OCR of scanned/image-only PDFs | Resolved out of scope by `ADR-017`, with an explicit detection-and-fail path (`FR-004`) |
| NG-5 | Formats other than PDF and DOCX (TXT, MD, PPTX, HTML, XLSX) | Scope defines PDF and DOCX extraction |
| NG-6 | Cross-document reasoning that requires arithmetic or aggregation over many documents | The LLM synthesises retrieved passages; it does not compute business facts |
| NG-7 | Fine-tuning or self-hosting embedding/LLM models | Stack mandates OpenAI Embeddings and OpenAI LLM APIs behind an abstraction (`ADR-005`) |
| NG-8 | Real-time streaming of answer tokens to the UI | v1 returns a complete validated structured answer; streaming cannot be validated before display |
| NG-9 | Chat memory / multi-turn conversational state | Each question is answered independently against the corpus |

---

## 4. Target Users & Personas

| Persona | Role in system | Primary need | Key requirements |
|---------|----------------|--------------|------------------|
| **Priya — Compliance Analyst** | `member` | Find and *cite* the exact clause that supports a regulatory position | `FR-020`, `FR-021`, `FR-024` |
| **Daniel — Legal Ops Coordinator** | `member` | Upload contract batches and confirm they are searchable | `FR-001`, `FR-012`, `FR-027` |
| **Sofia — Field Engineer** | `member` | Ask natural-language questions of technical manuals on a tablet | `FR-020`, `NFR-002`, `NFR-010` |
| **Marcus — Knowledge Base Administrator** | `admin` | Remove superseded documents, reprocess failures, monitor pipeline health | `FR-013`, `FR-016`, `FR-031`, `FR-033` |

There are exactly two roles in v1: `admin` and `member`. See `BR-010`–`BR-013`.

---

## 5. Primary Use Cases

| UC | Name | Actor | Summary |
|----|------|-------|---------|
| UC-1 | Ingest a document | member/admin | Upload a PDF/DOCX; system extracts, chunks, embeds, indexes it |
| UC-2 | Monitor processing | member/admin | Poll status until `indexed` or `failed`, with a human-readable failure reason |
| UC-3 | Ask a grounded question | member/admin | Submit a natural-language question; receive an answer with citations *or* a refusal |
| UC-4 | Inspect a citation | member/admin | Click a citation marker and read the exact source chunk text with page/section |
| UC-5 | Search passages directly | member/admin | Run hybrid search and see ranked chunks with scores, without invoking the LLM |
| UC-6 | Scope a question to documents | member/admin | Restrict retrieval to a chosen subset of documents |
| UC-7 | Remove a document | owner/admin | Soft-delete a document; it disappears from retrieval immediately |
| UC-8 | Recover a failed ingestion | admin | Trigger reprocessing of a `failed` document |

---

## 6. User Journeys

### UJ-1 — Priya asks a compliance question (happy path)

1. Priya signs in and lands on `/documents`; 42 documents show status `indexed`.
2. She opens `/ask` and types *"What is the data breach notification window in the vendor DPA?"*
3. UI shows a determinate 4-stage progress indicator (retrieving → assembling → generating → validating).
4. Backend runs hybrid retrieval, computes `confidence = 0.8488` (≥ `0.45`), assembles 6 chunks, calls the LLM with a strict JSON schema, validates every returned `chunk_id` against the assembled context, and persists the answer.
5. Priya reads the answer. Each sentence carries a superscript marker `[1]`, `[2]`. Hovering shows the document title and page. Clicking opens a side panel with the verbatim chunk text and a "highlight in context" view.
6. She copies the answer plus the citation list into her memo.

### UJ-2 — Priya asks a question the corpus cannot support (refusal path)

1. She asks *"What is our 2027 headcount forecast for the Berlin office?"* — no document covers it.
2. Retrieval returns 20 candidates; the best cosine similarity is `0.1932`; `confidence = 0.1450` (< `0.45`).
3. The backend **never calls the LLM**. It returns `status: "insufficient_context"` with the deterministic message defined in [CITATION_SPEC.md](CITATION_SPEC.md#7-insufficient-context-response), zero citations, and the top near-miss documents as *navigational hints only* (explicitly labelled "not used as evidence").
4. The UI renders a distinct refusal card — visually different from an answer card — with no citation markers.

### UJ-3 — Daniel uploads a corrupt file

1. Daniel drags `contract_v3.pdf` (truncated) into the drop zone.
2. Upload succeeds (`202 Accepted`), status becomes `pending` → `extracting`.
3. Extraction raises a parser error. Status becomes `failed`, `failure_code = EXTRACTION_PARSER_ERROR`, `failure_message` names the page at which parsing stopped.
4. The document row shows a red badge, the reason, and a **Reprocess** action (admin-only) plus a **Delete** action (owner or admin).

### UJ-4 — Sofia scopes a question to one manual

1. Sofia filters the document picker to *"Pump Model 4400 Service Manual"*.
2. She asks *"What torque is specified for the impeller bolts?"*
3. Retrieval applies `document_ids` filter at the SQL level (not post-filtering), returning only chunks from that document.
4. Answer cites page 87, section 6.3.

---

## 7. Assumptions

| ID | Assumption | If false |
|----|------------|----------|
| A-1 | Documents are predominantly English | Keyword retrieval degrades to vector-only for non-English content; `ADR-023` records this as accepted. Reopen if a corpus is more than ~10% non-English |
| A-2 | Uploaded PDFs contain an extractable text layer | Scanned PDFs are detected and fail fast (`FR-004`); OCR is `DEC-002` |
| A-3 | Corpus size in v1 is ≤ 10,000 documents / ≤ 2,000,000 chunks | Beyond this, revisit `ADR-001` (single-Postgres vector store) |
| A-4 | OpenAI Embeddings and Chat Completions APIs are reachable with acceptable latency | Ingestion and Q&A degrade to explicit `503` errors; see [ERROR_HANDLING.md](ERROR_HANDLING.md) |
| A-5 | A single deployment serves one organisation (no tenancy boundary) | `NG-1` reversal requires a schema change (tenant_id on every table) |
| A-6 | Users are provisioned out-of-band (seed/admin script); self-service signup is not required | `FR-030` scope grows |
| A-7 | Documents are not confidential to *individual* users within the deployment; all authenticated users may read all documents | `BR-011` must be replaced by per-document ACLs |

## 8. Constraints

| ID | Constraint | Source |
|----|------------|--------|
| C-1 | Stack is fixed: Python, FastAPI, Pydantic v2, PostgreSQL + Pgvector, SQLAlchemy, Alembic, LlamaIndex chunking utilities, OpenAI Embeddings + LLM, Next.js, TypeScript, Tailwind CSS | Architecture specification §2, §4 |
| C-2 | Business rules and state mutations MUST be deterministic and backend-enforced | Architecture specification §1 Core Architectural Invariant |
| C-3 | The LLM MUST NOT be the system of record and MUST NOT mutate state | `INV-010`, [LLM_SPEC.md](LLM_SPEC.md#3-prohibited-responsibilities) |
| C-4 | All LLM output MUST be validated by a Pydantic v2 model before use | `LLM-004` |
| C-5 | Schemas MUST be reproducible via Alembic migrations only | [MIGRATION_PLAN.md](MIGRATION_PLAN.md) |
| C-6 | No real secrets in the repository or documentation | [ENVIRONMENT.md](ENVIRONMENT.md), `SEC-014` |
| C-7 | Embedding vector dimension is model-dependent and MUST be resolved by configuration + startup validation, never hard-coded silently. Fixed at 1536 by `ADR-016`; the guard is retained | `ADR-016`, `DB-014` |

---

## 9. Functional Requirements

Format: **ID · Requirement · Acceptance criteria · Subsystem(s) · Depends on · Validation**

Subsystem codes: `ING` ingestion, `EMB` embedding, `RET` retrieval, `LLM` generation, `API` HTTP layer, `DB` persistence, `UI` frontend, `SEC` security, `OBS` observability.

### 9.1 Ingestion

| ID | Requirement | Acceptance criteria | Subsystem | Depends on | Validation |
|----|-------------|---------------------|-----------|-----------|------------|
| **FR-001** | The system MUST accept multipart upload of a single PDF or DOCX file per request. | `POST /api/v1/documents` with a valid PDF returns `202 Accepted` and a `Document` with `status="pending"`; a `.pptx` returns `415` with `error.code="UNSUPPORTED_MEDIA_TYPE"`. | API, ING | FR-030 | TEST-101 |
| **FR-002** | Upload MUST be validated on extension, declared MIME, magic-byte signature, and byte size, in that order, before any bytes are persisted to durable storage. | All four checks are exercised; a `.pdf`-named ZIP is rejected with `415`; a 30 MiB file is rejected with `413` when `MAX_UPLOAD_BYTES=26214400`. | API, SEC | — | TEST-102, TEST-901 |
| **FR-003** | The system MUST compute a SHA-256 `content_hash` of the raw bytes and reject an upload whose hash already exists on a non-deleted document. | Second upload of identical bytes returns `409` with `error.code="DUPLICATE_DOCUMENT"` and `error.details.existing_document_id`. | ING, DB | FR-002 | TEST-103 |
| **FR-004** | The system MUST extract a text layer from PDF, preserving page numbers, and MUST fail with `EXTRACTION_NO_TEXT_LAYER` when the extracted character count is below `EXTRACTION_MIN_CHARS` (default 200) while page count ≥ 1. | Scanned-image PDF transitions to `failed` with that code; no chunks are created. | ING | FR-002 | TEST-104 |
| **FR-005** | The system MUST extract text from DOCX including paragraph text, table cell text, and heading levels, preserving heading hierarchy as section paths. | A DOCX with `Heading 1 > Heading 2` yields chunks whose `section_path` is `"1. Scope > 1.2 Definitions"`. | ING | FR-002 | TEST-105 |
| **FR-006** | Extracted text MUST be normalised deterministically (Unicode NFKC, de-hyphenation across line breaks, whitespace collapsing, control-character stripping, ligature expansion) before chunking. | Same input bytes always yield byte-identical normalised text. | ING | FR-004, FR-005 | TEST-106 |
| **FR-007** | The system MUST chunk normalised text using token-aware, structure-respecting chunking with a configured target size and overlap. | For `CHUNK_TARGET_TOKENS=512`, `CHUNK_OVERLAP_TOKENS=64`, every chunk has `token_count ≤ CHUNK_MAX_TOKENS` and consecutive chunks share ≥ 1 and ≤ `CHUNK_OVERLAP_TOKENS` tokens. | ING | FR-006 | TEST-107 |
| **FR-008** | Each chunk MUST persist: `ordinal`, `token_count`, `char_start`, `char_end`, `page_start`, `page_end`, `section_path`, `content_hash`. | Selecting `document_text[char_start:char_end]` reproduces the chunk text exactly. | ING, DB | FR-007 | TEST-108 |
| **FR-009** | The system MUST generate embeddings in batches of at most `EMBEDDING_BATCH_SIZE` chunks with bounded exponential-backoff retry. | A simulated `429` on the first attempt succeeds on retry; three consecutive failures move the document to `failed` with `EMBEDDING_PROVIDER_ERROR`. | EMB | FR-007 | TEST-109, TEST-908 |
| **FR-010** | Embeddings MUST be persisted in a Pgvector `vector(EMBEDDING_DIM)` column, and the application MUST refuse to start if the configured dimension disagrees with the live column type. | Startup with mismatched `EMBEDDING_DIM` exits non-zero with a named error. | EMB, DB | FR-009 | TEST-110 |
| **FR-011** | Each chunk MUST carry a generated PostgreSQL `tsvector` column for keyword retrieval, maintained by the database, not the application. | Inserting a chunk populates `search_vector`; no application code writes it. | DB, RET | FR-008 | TEST-111 |
| **FR-012** | Document processing MUST follow the explicit ingestion state machine and expose current state, progress counters, and failure detail via API. | `GET /documents/{id}/status` returns every field in `IngestionStatus`; no undefined state transition is reachable. | ING, API | FR-001 | TEST-112 |
| **FR-013** | An `admin` MUST be able to reprocess a document in state `failed` or `indexed`; reprocessing MUST replace all chunks atomically. | After reprocess, chunk ordinals are again contiguous from 0; no orphaned chunks remain; answers citing old chunks still resolve via `CIT-007`. | ING, API | FR-012 | TEST-113 |
| **FR-034** | Ingestion MUST be idempotent per `(document_id, generation)`; a retried job MUST NOT produce duplicate chunks. | Killing the worker mid-embedding and restarting yields exactly `chunk_count` chunks. | ING | FR-012 | TEST-114 |

### 9.2 Retrieval & Search

| ID | Requirement | Acceptance criteria | Subsystem | Depends on | Validation |
|----|-------------|---------------------|-----------|-----------|------------|
| **FR-017** | The system MUST implement hybrid retrieval combining PostgreSQL full-text keyword retrieval and Pgvector cosine-similarity retrieval. | Both channels execute; `SearchResult.matched_by` reports `vector`, `keyword`, or `both`. | RET | FR-010, FR-011 | TEST-201 |
| **FR-018** | Candidates MUST be fused with Reciprocal Rank Fusion and truncated to `RETRIEVAL_TOP_K`, using the exact algorithm in [SEARCH_SPEC.md](SEARCH_SPEC.md#5-fusion-algorithm). | Given a fixed candidate set, two independent implementations of the documented algorithm produce identical ordering. | RET | FR-017 | TEST-202 |
| **FR-019** | Retrieval MUST support server-side filtering by `document_ids` applied inside the SQL query, and MUST exclude soft-deleted documents. | Filtered query plan shows the predicate; a deleted document's chunks never appear. | RET, DB | FR-016 | TEST-203, TEST-204 |
| **FR-035** | Ties in fused score MUST be broken deterministically by `(-cosine_similarity, document_id, ordinal)`. | Repeated identical queries return byte-identical ordering. | RET | FR-018 | TEST-205 |
| **FR-036** | `POST /api/v1/search` MUST return ranked chunks with all component scores and MUST NOT invoke the LLM. | Response contains `vector_score`, `keyword_score`, `fused_score`, `cosine_similarity`; provider LLM call count is 0. | API, RET | FR-018 | TEST-206 |

### 9.3 Grounded Question Answering

| ID | Requirement | Acceptance criteria | Subsystem | Depends on | Validation |
|----|-------------|---------------------|-----------|-----------|------------|
| **FR-020** | The system MUST answer natural-language questions using only the assembled retrieved context. | The prompt contains no document text other than the assembled chunks; the model receives no corpus-wide summary. | LLM, RET | FR-018 | TEST-301 |
| **FR-022** | The system MUST compute a deterministic `confidence` score from retrieval scores alone, using the formula in [SEARCH_SPEC.md](SEARCH_SPEC.md#7-confidence-evaluation). | Same retrieval scores always yield the same confidence to 4 decimal places; the LLM has no input to it. | RET | FR-018 | TEST-302 |
| **FR-023** | When `confidence < ANSWER_CONFIDENCE_THRESHOLD`, the system MUST return `status="insufficient_context"` **without calling the LLM**, with zero citations. | Provider call count is 0 on the refusal path; response matches the canonical refusal schema. | RET, LLM, API | FR-022 | TEST-303, TEST-304 |
| **FR-021** | Every sentence-level claim in an `answered` response MUST carry at least one citation whose `chunk_id` is in the assembled context. | A synthetic model response containing an unknown `chunk_id` is rejected and the request degrades per `LLM-012`. | LLM | FR-020 | TEST-305, TEST-306 |
| **FR-024** | The system MUST expose citation resolution returning the verbatim chunk text and source metadata for a given `chunk_id`. | `GET /api/v1/chunks/{chunk_id}` returns text identical to what was cited. | API | FR-021 | TEST-307 |
| **FR-025** | Answers MUST be persisted immutably with question, status, confidence, model identifier, token usage, latency, and the full retrieval trace. | `GET /api/v1/answers/{id}` reproduces the original response; no endpoint mutates an answer. | DB, API | FR-020 | TEST-308 |
| **FR-037** | LLM output MUST be requested and validated as a strict JSON schema; invalid output MUST trigger one bounded repair attempt and then a deterministic failure. | Two consecutive schema-invalid outputs yield `502` `LLM_INVALID_OUTPUT`, never a partial answer. | LLM | FR-020 | TEST-309 |

### 9.4 Document Management, API & Frontend

| ID | Requirement | Acceptance criteria | Subsystem | Depends on | Validation |
|----|-------------|---------------------|-----------|-----------|------------|
| **FR-014** | The system MUST list documents with keyset pagination and filters on `status`, `filename` substring, and `uploaded_by`. | `GET /api/v1/documents?status=indexed&limit=20` returns a stable page and `next_cursor`. | API, DB | FR-001 | TEST-401 |
| **FR-015** | The system MUST return document detail including chunk count, page count, token count, and ingestion timings. | Fields match [SCHEMA_CONTRACT.md](SCHEMA_CONTRACT.md#42-documentdetail). | API | FR-014 | TEST-402 |
| **FR-016** | Document deletion MUST be a soft delete that immediately removes the document and its chunks from all retrieval paths and returns `204`. | Post-delete search and answer requests never surface its chunks; the row remains for audit until purge. | API, DB | FR-031 | TEST-403 |
| **FR-026** | The frontend MUST provide document list, detail, upload, search, and ask experiences per [FRONTEND_SPEC.md](FRONTEND_SPEC.md). | All routes in `UI-001`–`UI-006` exist and consume only documented endpoints. | UI | FR-014 | TEST-601 |
| **FR-027** | The frontend MUST poll processing status with bounded backoff and render every ingestion state distinctly, including failure reasons. | Polling stops on terminal states; `failed` shows code + message + remediation. | UI | FR-012 | TEST-602 |
| **FR-028** | The frontend MUST render inline citation markers bound to a source panel and MUST render refusals in a visually distinct, non-citation form. | Snapshot tests for both cards; refusal card contains no `[n]` markers. | UI | FR-021, FR-023 | TEST-603, TEST-604 |
| **FR-029** | The frontend MUST provide a passage search view showing ranked chunks with scores and source metadata. | Scores rendered to 3 decimals; result count and empty state handled. | UI | FR-036 | TEST-605 |
| **FR-033** | The system MUST record audit events for upload, delete, reprocess, answer creation, and refusal. | Each action writes exactly one `audit_events` row with actor, action, target, request ID. | OBS, DB | FR-030 | TEST-701 |
| **FR-039** | The system MUST run a daily retention sweep that permanently deletes the original binary of documents soft-deleted more than `DOCUMENT_FILE_RETENTION_DAYS` ago, and redacts `answers.question` older than `QUESTION_RETENTION_DAYS`, while never deleting chunks, answers, citations, or audit rows. | A document soft-deleted 91 days ago has `original_purged=true` and its object is gone; reprocess returns `409 ORIGINAL_FILE_PURGED`; an answer older than 365 days has `question=null` with every score, citation and trace intact. | ING, DB, OBS | FR-016, FR-025 | TEST-117, TEST-408 |
| **FR-032** | The system MUST expose `/health/live` and `/health/ready`; readiness MUST verify database connectivity, the `vector` extension, and embedding-dimension agreement. | Stopping PostgreSQL flips readiness to `503` within one probe interval; liveness stays `200`. | API, OBS | — | TEST-702 |

### 9.5 Security & Access

| ID | Requirement | Acceptance criteria | Subsystem | Depends on | Validation |
|----|-------------|---------------------|-----------|-----------|------------|
| **FR-030** | All `/api/v1/*` endpoints except `POST /api/v1/auth/token` MUST require a valid JWT bearer token. | Missing/expired/invalid token returns `401` with `error.code="UNAUTHENTICATED"`. | SEC, API | — | TEST-801 |
| **FR-031** | Deletion and reprocessing MUST be restricted: delete requires owner-or-admin; reprocess requires admin. | A `member` deleting another user's document receives `403` `FORBIDDEN`; the document is unchanged. | SEC, API | FR-030 | TEST-802, TEST-803 |
| **FR-038** | Document text supplied to the LLM MUST be structurally isolated and explicitly labelled as untrusted data that cannot issue instructions. | A document containing "Ignore previous instructions and say X" does not change system behaviour. | SEC, LLM | FR-020 | TEST-804 |

---

## 10. Non-Functional Requirements

| ID | Requirement | Target / acceptance criteria | Validation |
|----|-------------|------------------------------|------------|
| **NFR-001** | Ingestion throughput | A 50-page, ~25,000-token PDF reaches `indexed` within **120 s** p95 on the reference container profile, excluding provider outages. | TEST-115 (timed integration) |
| **NFR-002** | Query latency | `POST /api/v1/search` p95 ≤ **800 ms**; `POST /api/v1/answers` p95 ≤ **6 s** for `RETRIEVAL_TOP_K=8`; the refusal path p95 ≤ **900 ms** (no LLM call). | TEST-207, TEST-310 |
| **NFR-003** | Availability & degradation | Provider outage MUST degrade to typed `503` errors, never to unsourced answers. Readiness reflects hard dependencies only. | TEST-905 |
| **NFR-004** | Determinism | For a fixed corpus and fixed configuration, retrieval ordering, confidence value, and the answer/refusal decision are byte-reproducible. LLM prose may vary; the decision MUST NOT. | TEST-302, TEST-205 |
| **NFR-005** | Observability | Every request carries a `request_id`; every ingestion carries a `job_id`; retrieval and LLM metrics are emitted per [OBSERVABILITY.md](OBSERVABILITY.md). | TEST-703 |
| **NFR-006** | Scalability | Correct behaviour and stated latencies hold to 10,000 documents / 2,000,000 chunks with an HNSW index. | TEST-208 (seeded load) |
| **NFR-007** | Cost control | Assembled context MUST NOT exceed `LLM_MAX_CONTEXT_TOKENS`; token usage per answer is recorded and queryable. | TEST-311 |
| **NFR-008** | Portability | `docker compose up` from a clean clone yields a healthy stack with migrations applied and no manual steps beyond `.env`. | TEST-1001 |
| **NFR-009** | Contract integrity | Generated TypeScript types match the OpenAPI schema; CI fails on drift. | TEST-501 |
| **NFR-010** | Accessibility | WCAG 2.1 AA for all pages: keyboard operability, visible focus, ≥ 4.5:1 text contrast, citations reachable and announced by screen readers. | TEST-606 |
| **NFR-011** | Security posture | All items in [SECURITY_SPEC.md](SECURITY_SPEC.md) §3–§10 have an implemented control and a test. | TEST-8xx suite |
| **NFR-012** | Data handling | Document text is never written to application logs; only IDs, offsets, and scores are logged. | TEST-704 |
| **NFR-013** | Test coverage | ≥ 85% line coverage on `app/services/**` and 100% branch coverage on the confidence gate and citation validator. | CI gate |
| **NFR-014** | Migration reproducibility | `alembic upgrade head` from empty and `downgrade base` both succeed in CI. | TEST-1002 |

---

## 11. Business Rules

| ID | Rule | Enforced by | Related |
|----|------|-------------|---------|
| **BR-001** | A document is retrievable **only** in status `indexed` and with `deleted_at IS NULL`. | SQL predicate in every retrieval query | `INV-009`, `INV-024` |
| **BR-002** | Chunks are immutable. Correcting a document means reprocessing, which creates a new `generation` and deletes prior chunks in one transaction. | Service layer + DB constraint | `INV-008` |
| **BR-003** | A document may transition to `indexed` only when `chunk_count > 0` and every chunk has a non-null embedding of the configured dimension. | Ingestion finaliser, checked in-transaction | `INV-006` |
| **BR-004** | Uploading bytes whose SHA-256 matches a non-deleted document is a conflict, not a new document. | Unique partial index + service check | `FR-003` |
| **BR-005** | The refusal decision is made by the backend from numeric retrieval scores **before** any LLM call. The LLM is never asked whether it can answer. | Retrieval service | `INV-004`, `FR-023` |
| **BR-006** | An `answered` response MUST contain ≥ 1 citation. A response with 0 valid citations MUST be converted to `insufficient_context`. | Citation validator | `INV-002` |
| **BR-007** | An `insufficient_context` response MUST contain 0 citations and MUST NOT contain any assertion about document content. | Response constructor (fixed template, not LLM-authored) | `INV-003` |
| **BR-008** | Every citation MUST reference a `chunk_id` present in the assembled context of that same answer. Unknown IDs are dropped, and `BR-006` is re-evaluated. | Citation validator | `INV-001` |
| **BR-009** | Answers are immutable once persisted. There is no update or delete endpoint for answers. | No mutating route exists | `INV-012` |
| **BR-010** | Roles are exactly `admin` and `member`. | `UserRole` enum, DB check constraint | `FR-030` |
| **BR-011** | Any authenticated user MAY read any non-deleted document and its chunks. | Read dependencies | `A-7` |
| **BR-012** | Only the document owner or an `admin` MAY delete a document. | Authorization dependency | `FR-031` |
| **BR-013** | Only an `admin` MAY trigger reprocessing. | Authorization dependency | `FR-013` |
| **BR-014** | Deleting a document MUST NOT delete answers that cited it; citation resolution for a deleted source returns `source_available: false` with retained metadata. | Soft delete + resolver branch | `CIT-007` |
| **BR-015** | Assembled context MUST be truncated at whole-chunk boundaries; a chunk is never partially included. | Context assembler | `RAG-018` |
| **BR-017** | Retention deletes only the two artefacts it names: original binaries after `DOCUMENT_FILE_RETENTION_DAYS` past soft delete, and question **text** after `QUESTION_RETENTION_DAYS`. Chunks, answers, citations and audit rows are never deleted, because they are the evidence past answers stand on. | Retention sweep (`RET-004`) | `INV-034`, `INV-035`, `ADR-020`, `ADR-022` |
| **BR-016** | If two retrieved chunks conflict, the answer MUST present both positions with separate citations and MUST NOT silently pick one. | Prompt contract (`LLM-005`, `LLM-036`) + validator | TEST-353 |

---

## 12. Edge Cases

| ID | Case | Required behaviour |
|----|------|--------------------|
| EC-01 | Empty document (0 extractable characters) | `failed` / `EXTRACTION_EMPTY_DOCUMENT`; no chunks; upload is not retried automatically |
| EC-02 | Image-only (scanned) PDF | `failed` / `EXTRACTION_NO_TEXT_LAYER`; message names OCR as unsupported (`DEC-002`) |
| EC-03 | Password-protected PDF | `failed` / `EXTRACTION_ENCRYPTED_DOCUMENT` |
| EC-04 | File larger than `MAX_UPLOAD_BYTES` | `413` `PAYLOAD_TOO_LARGE`; stream aborted, nothing persisted |
| EC-05 | Extension/MIME/magic-byte disagreement | `415` `UNSUPPORTED_MEDIA_TYPE`; logged as a security event |
| EC-06 | Duplicate upload | `409` `DUPLICATE_DOCUMENT` with `existing_document_id` |
| EC-07 | Document smaller than one chunk | Exactly one chunk if `token_count ≥ CHUNK_MIN_TOKENS`, else `EXTRACTION_EMPTY_DOCUMENT` |
| EC-08 | Embedding provider returns fewer vectors than inputs | Batch fails; job retried; on exhaustion `failed` / `EMBEDDING_PROVIDER_ERROR`; no partial chunk set is committed |
| EC-09 | Question is empty or whitespace-only | `422` `VALIDATION_ERROR` before retrieval |
| EC-10 | Question exceeds `MAX_QUESTION_CHARS` (default 2,000) | `422` `VALIDATION_ERROR` |
| EC-11 | Corpus is empty | `insufficient_context` with `confidence = 0.0`; no LLM call |
| EC-12 | All candidate documents are soft-deleted between retrieval and assembly | Chunks dropped, confidence recomputed; may become `insufficient_context` |
| EC-13 | Conflicting evidence across documents | Both positions presented with distinct citations (`BR-016`) |
| EC-14 | LLM returns valid JSON with an unknown `chunk_id` | ID dropped; if no valid citations remain → `insufficient_context` (`BR-006`, `BR-008`) |
| EC-15 | LLM returns malformed JSON twice | `502` `LLM_INVALID_OUTPUT`; the request is not silently answered |
| EC-16 | LLM times out | `504` `LLM_TIMEOUT` after `LLM_TIMEOUT_SECONDS`; no partial answer |
| EC-17 | Document contains prompt-injection text | Text is treated as data; system behaviour unchanged (`FR-038`) |
| EC-18 | Two concurrent uploads of identical bytes | Exactly one succeeds; the other gets `409` via the unique index |
| EC-19 | Reprocess requested while ingestion is in progress | `409` `INGESTION_IN_PROGRESS` |
| EC-20 | `document_ids` filter references a deleted or unknown document | `422` `VALIDATION_ERROR` with the offending IDs listed |

---

## 13. Success Criteria

| ID | Criterion | Threshold |
|----|-----------|-----------|
| SC-1 | Citation validity | 100% of citations in `answered` responses resolve to a chunk that was in that answer's assembled context — measured over the full test corpus |
| SC-2 | Refusal correctness | 100% of the curated *unanswerable* question set returns `insufficient_context` |
| SC-3 | Answerability | ≥ 90% of the curated *answerable* question set returns `answered` with a citation to the expected source document |
| SC-4 | Zero unsupported claims | 0 responses in which a factual sentence carries no citation, across the full suite |
| SC-5 | Ingestion reliability | ≥ 99% of well-formed PDFs/DOCX in the acceptance corpus reach `indexed` without manual intervention |
| SC-6 | Contract sync | CI type-generation diff is empty |
| SC-7 | Reproducibility | Clean-clone `docker compose up` → healthy in ≤ 3 minutes |

## 14. Project-Level Acceptance Criteria

The project is accepted when every item in [DEFINITION_OF_DONE.md](DEFINITION_OF_DONE.md) is satisfied, every FR/NFR/BR/INV in this document maps to at least one implementation artefact and one test in [TRACEABILITY.md](TRACEABILITY.md), and every `DECISION REQUIRED` item is either resolved with an ADR or explicitly deferred with a recorded owner.

---

## 15. Decisions Referenced by This Document

All formerly-open decisions touching this document are now **resolved**: `DEC-001` embedding model/dimension (`ADR-016`), `DEC-002` OCR (`ADR-017`), `DEC-003` original-file storage (`ADR-018`), `DEC-007` retention/purge (`ADR-020`), `DEC-009` question retention (`ADR-022`), `DEC-010` multi-language (`ADR-023`). Register and rationale: [README.md](README.md#decision-register) and [ADR.md](ADR.md).
