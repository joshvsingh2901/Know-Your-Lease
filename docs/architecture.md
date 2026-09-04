# Architecture

The current system is a browser application, a FastAPI service with inline-development or SQS-worker ingestion, local-or-S3 private document storage, Voyage AI embeddings, exact PostgreSQL + pgvector retrieval, Gemini grounded answer generation, verified citation snippets, answer reuse, and PDF source inspection. The original indexing pipeline remains intact behind a durable production queue boundary. Cognito-backed authentication and per-document ownership gate every document-scoped operation.

## Current system

```text
Browser / Next.js
  ↓ multipart PDF
FastAPI upload endpoint
  ↓
DocumentStorage → safe local storage or private S3
  ↓ SQS document identifier (production) or FastAPI BackgroundTasks (local)
Standalone ingestion worker
  ↓
PyMuPDF page extraction
  ↓
Conservative normalization
  ↓
Page-scoped paragraph/sentence chunking
  ↓ batches using input_type=document
Voyage AI (voyage-law-2)
  ↓ 1024-dimensional vectors
DocumentChunk records
  ↓
PostgreSQL 18 + pgvector
  ↑ exact document-scoped cosine search
Voyage query embedding ← question ← Next.js question UI
  ↓ selected lease excerpts only
Gemini structured grounded generation
  ↓ validated SOURCE_n identifiers and supporting quotes
Backend verifies quotes against retrieval chunks
  ↓ bounded deterministic fallback when needed
Backend-owned page metadata and concise source snippets
  ↓
Answer, compact citation cards, and PDF page navigation
```

- `frontend/` owns file selection, upload feedback, polling, single-turn questions, a responsive side-by-side PDF viewer, answer display, and compact source cards. Citation interaction changes the viewer page and visibly selects the source card.
- `backend/app/api/routes/documents.py` owns upload validation plus document-library, PDF, development-debug, and question contracts.
- `backend/app/api/document_access.py` is the single route-level document access boundary. It resolves a document only when `Document.owner_id` matches the authenticated `current_user`; every document-scoped route depends on it rather than querying `Document` independently.
- `backend/app/api/auth_dependencies.py` and `backend/app/core/auth.py` own identity: `require_current_user` resolves the authenticated `User` (Cognito JWT verification in production, a fixed local-development user when `AUTH_MODE=disabled`), and every document-scoped route requires it.
- `backend/app/services/storage.py` defines `DocumentStorage` plus local and S3 implementations. Both use internal `uploads/<uuid>.pdf` keys; original filenames are metadata only.
- `backend/app/services/pdf_extraction.py`, `text_normalization.py`, and `chunking.py` form an inspectable preprocessing pipeline with no LLM or orchestration framework.
- `backend/app/services/embeddings.py` batches document chunks, applies account-aware pacing and bounded transient retries, and validates Voyage output.
- `backend/app/services/document_ingestion.py` owns status transitions and the final all-or-nothing chunk persistence transaction.
- `backend/app/services/ingestion_queue.py` owns the versioned SQS publisher/consumer boundary, and `backend/app/workers/ingestion.py` owns standalone polling and acknowledgement orchestration.
- `backend/app/services/retrieval.py` performs exact cosine search with a mandatory `document_id` predicate, retrieves 10 candidates, and diversifies them to at most 5 results.
- `backend/app/services/generation.py` isolates the official Google GenAI client, structured JSON response schema, grounding prompt, prompt-injection boundary, source-ID validation, abstention behavior, and one bounded retry for transient provider overload.
- `backend/app/services/citation_snippets.py` validates model quotes against source chunks and provides bounded sentence-aware fallback snippets plus conservative heading detection.
- `backend/app/services/question_answering.py` requires a ready document, coordinates query embedding, retrieval, generation, verified snippets, and backend citation mapping.
- `backend/app/models/` contains `User`, `Document` (owned by exactly one `User` through `owner_id`), and document-owned `DocumentChunk` records.
- `grounded_answer_cache` stores document-scoped, versioned, verified final answers for exact normalized question reuse.
- `backend/alembic/` is the only production schema mechanism; application startup does not create tables.

## Request and processing lifecycle

```text
POST /documents
  ↓ validate filename, media type, %PDF- signature, and size
Persist bytes atomically under a UUID storage key
  ↓
Insert Document(status=queued, current_ingestion_version=1) in SQS mode
  ↓ publish {version, document_id, ingestion_version} and return 201
Standalone worker long-polls and validates the message
  ↓
Document(status=processing)
  ↓
Extract pages → normalize → chunk → embed
  ↓ one database transaction
Delete any stale chunks → insert complete new index → status=ready
```

A retryable extraction dependency or persistence failure returns the document to `queued`; a permanent document failure records `failed` plus a short safe message. Existing committed chunks remain untouched until one final transaction replaces them, invalidates cache entries, records the completed ingestion version, and marks `ready`. A `ready` status therefore means that the complete chunk text, provenance, and vectors were persisted successfully for the current version.

## Question lifecycle

```text
POST /documents/{document_id}/questions
  ↓ validate UUID and a non-blank question of at most 1,000 characters
Require Document(status=ready)
  ↓
Voyage voyage-law-2 embedding (input_type=query)
  ↓
SELECT chunk metadata and cosine distance
WHERE DocumentChunk.document_id = requested document
ORDER BY cosine distance ASC
LIMIT 10
  ↓
Remove near-identical overlap; retain at most 5 distinct chunks
  ↓ assign SOURCE_1 ... SOURCE_n
Gemini JSON generation using only those excerpts
  ↓ validate answer, source IDs, and supporting quotes
Verify each quote occurs in its corresponding chunk
  ↓ use deterministic bounded fallback if it does not
Map source IDs to database-owned chunk IDs/pages/snippets/scores
  ↓
Return answer and citations
```

`POST /documents/{document_id}/retrieve` runs the same ready check, query embedding, exact search, and diversification but skips Gemini. It is a development diagnostic for separating retrieval quality from generation quality. Neither endpoint returns vector arrays.

Repeated questions first check `grounded_answer_cache` using the document ID, whitespace/case-normalized exact question, and a cache version. A hit returns the already verified answer/citations without calling Voyage or Gemini; only a successful non-abstaining response with verified citations is stored.

## Persistence and isolation

The original PDF lives in the configured `DocumentStorage`: the gitignored `backend/storage/uploads/` default, another `PDF_STORAGE_DIR`, or a private S3 bucket. UUIDs generate identical opaque keys across backends; original filenames are display metadata only. Local resolution rejects traversal, S3 performs direct key operations without listing or public URLs, and API responses never expose internal locations. Each chunk and cache row has a required foreign key to exactly one document with intentional delete cascade. Retrieval includes a `document_id` SQL filter before ranking and applies a second defensive scope check in orchestration; there is intentionally no global corpus search design.

`GET /documents` returns only the authenticated user's own documents. The frontend can reopen a ready record without processing it again. Metadata, list, PDF, question, chunk, and retrieval routes all pass through the centralized route access boundary, which enforces `owner_id` ownership; a document that does not exist and a document owned by someone else both return 404, never 403, so a document UUID cannot be used to probe for another user's document. A document with no owner (`owner_id IS NULL`, a pre-authentication legacy row) matches no user and is inaccessible to everyone until explicitly assigned. Browser localStorage remembers only the active UUID and is never an access-control mechanism: the backend re-checks ownership on every request regardless of what a client claims to have open.

The vector column has 1024 dimensions to match `voyage-law-2`. Conventional document/page indexes and a unique per-document chunk order support isolation and inspection. There is no ANN index: a normal lease contains few enough chunks that exact cosine distance is simpler and sufficiently fast.

## Grounding and citation boundary

Gemini receives only the final retrieved excerpts, never the complete lease or PDF. Trusted system instructions are separate from a JSON-encoded untrusted question/evidence payload. The system instruction treats both the question and lease excerpts as untrusted data, forbids following embedded commands, outside legal knowledge, and legal advice, and requires supplied `SOURCE_n` identifiers. The provider response is validated against a strict JSON schema. Unknown identifiers reject the response at both generation and orchestration boundaries; duplicate valid identifiers are deduplicated; and a response with no valid citations is replaced by the fixed abstention answer.

Page numbers, section titles, snippets, similarity scores, and chunk IDs are mapped from retrieval results in backend code. A model-provided quote is used only after whitespace-normalized containment validation against its matching chunk. It never controls page metadata, and an invalid quote is replaced by a local relevant-sentence fallback.

`GET /documents/{document_id}/pdf` reads only the document's already-owned storage key through the configured backend and serves it as `application/pdf` without exposing a path, bucket, or key. At ready state, the frontend presents a two-column workspace on desktop: the PDF viewer on the left and the question/answer panel on the right. Citation actions jump the viewer to the cited page, then attempt a whitespace-normalized match against React-PDF's rendered text-layer spans. Only matching spans are highlighted; an imperfect match leaves the correct page visible without a fabricated highlight.

## Processing boundary

`INGESTION_MODE=inline` retains FastAPI `BackgroundTasks` for AWS-free development. `INGESTION_MODE=sqs` makes the request process publish only a versioned document identifier; a standalone worker with independent database sessions invokes the unchanged ingestion pipeline. Atomic claims, ingestion/attempt versions, row-locked completion checks, and the existing chunk uniqueness constraint make duplicate delivery safe. Completed, stale, and recorded-terminal-failure messages are acknowledged, since each of those outcomes is already durably persisted on the document row; retryable, malformed, missing, future-version, and busy messages remain for SQS redelivery/redrive. This is at-least-once delivery plus idempotent processing, not exactly-once delivery.

## Authentication and authorization boundary

`AUTH_MODE=cognito` requires `Authorization: Bearer <access token>`. `backend/app/core/auth.py` verifies the token's signature against cached Cognito JWKS (by `kid`, refetched on a normal TTL and, separately, once on an unknown `kid` under its own cooldown so a token carrying a random `kid` cannot force repeated outbound JWKS fetches), issuer, `token_use == "access"` (never an ID token), and `client_id` -- Cognito access tokens carry no `aud` claim, so `client_id` is the audience check. A verified subject is resolved or just-in-time provisioned into a local `users` row keyed by `cognito_sub`; the backend never stores a password or contacts Cognito's user-management API. `AUTH_MODE=disabled` (the local development and test default) skips token verification and resolves every request to one fixed local-development user, so the ownership seam itself is still exercised, not bypassed. See `docs/authentication.md` for the full design and current limitations.

## Deployment boundary

The approved Phase 6 target deploys `frontend/` to Vercel and exposes the API through an HTTPS Application Load Balancer. One ECR image supports three ECS/Fargate workloads: the default Uvicorn API service, `python -m app.workers.ingestion` as a worker service, and `alembic upgrade head` as a one-off migration task. The initial API and worker each use 0.25 vCPU, 1 GiB, and desired count one in public task subnets; RDS PostgreSQL with pgvector remains in isolated subnets. The region is `ca-central-1`, and no NAT Gateway is planned initially.

Each workload uses the shared `Settings` object but has an explicit validation entry point. API validation covers database, S3, SQS, Cognito, the exact frontend origin, Voyage, Gemini, and debug safety. Worker validation covers only database, S3, SQS, the processing timeout, and Voyage. Alembic validates only the production database URL. This keeps Cognito, frontend, and Gemini configuration out of the worker and keeps all non-database application configuration out of migrations. Phase 6A prepares this boundary only; no AWS or Vercel resource has been created or deployed.

## Production boundaries and current limitations

Provider and database exceptions never flow directly into API responses. Known provider 429 and 5xx failures return safe structured errors distinct from missing or invalid configuration and unexpected provider failures. Logs retain document IDs, counts, timings, provider status/type/request IDs, and stack traces where useful, but omit API keys, raw provider bodies, prompts, and extracted lease text.

Configuration masks database/provider secrets in settings representations. Development remains key-optional. A production API requires an explicit database URL, S3 storage, SQS ingestion, Cognito authentication, both provider keys, an HTTPS non-loopback frontend origin, and disabled debug endpoints. A production worker requires an explicit database URL, S3, SQS, and Voyage but not Cognito, frontend CORS, or Gemini. Production migrations require only an explicit database URL. CORS accepts validated explicit HTTP(S) origins only: configured local origins in development and only `FRONTEND_ORIGIN` outside development. Chunk/retrieval debug endpoints default on only in development and return 404 when disabled.

The current system implements Cognito authentication and per-document ownership in application code (see above), but does not provision a live Cognito user pool, provisioned S3/SQS infrastructure or lifecycle/KMS/redrive policy, automated DLQ replay, visibility heartbeats, OCR, cross-process rate limiting, chat history, query rewriting, reranking, hybrid/full-text retrieval, coordinate-level PDF highlights, or a calibrated relevance threshold. There is also no re-ingestion endpoint or other producer that advances a document past ingestion version 1; the version/attempt machinery that protects against duplicate and stale delivery has no caller that requests a later version yet. Text-layer highlighting is best-effort because PDFs can expose text with imperfect spacing. Abstention relies on evidence-limited prompting plus strict source-ID validation, not a calibrated score cutoff or a second faithfulness model.
