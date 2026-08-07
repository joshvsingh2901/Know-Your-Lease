# Production Hardening

## Reuse and local library

Documents are durable backend records. Uploading persists a UUID-owned PDF, its chunks, and a ready status; reopening a listed ready document, refreshing the browser, and asking later questions reuse those records without extraction or document embeddings. The browser stores only the active UUID in localStorage for convenience. It is not an authorization boundary.

`GET /documents` is a deliberately small single-user/local library API. It returns safe metadata only and the frontend presents ready documents as compact reopen buttons beside upload. `backend/app/api/document_access.py` is the shared access seam used by list, metadata, PDF, question, cache entry points, chunks, and retrieval routes. It intentionally exposes all documents locally. A future authenticated deployment must add the current principal and an owner/tenant predicate there; no fake ownership field or localStorage-based access control exists today.

## Answer reuse

`grounded_answer_cache` stores a final answer and already-verified citation payload only after a successful grounded response with at least one citation. Its unique key is document UUID, whitespace/case-normalized exact question, and `ANSWER_CACHE_VERSION`. The same exact normalized question therefore skips Voyage and Gemini on later requests; paraphrases do not collide. Semantic caching was deliberately excluded because superficially similar legal questions can differ materially, and no labeled data supports a safe similarity threshold. Provider failures, empty-evidence results, and abstentions are not cached. Cache reads revalidate cited chunk IDs against the requested document; document deletion cascades cache deletion, re-indexing invalidates that document's prior answers, and a version bump invalidates entries after material prompt or response-format changes.

## Provider and debug boundaries

Question failures use safe structured API errors. A known 429 returns `provider_rate_limited`; a known upstream 5xx returns `provider_temporarily_unavailable`; missing or invalid configuration returns `provider_configuration`; other provider failures return `provider_request_failed`. Provider payloads, keys, and stack traces never reach the browser. Existing bounded retries remain the only automatic retries.

Chunk inspection and retrieval diagnostics are enabled by default only when `ENVIRONMENT=development`. Set `DEBUG_ENDPOINTS_ENABLED=true` deliberately for a non-development diagnostic environment; otherwise `/chunks` and `/retrieve` return 404. Normal document metadata, PDF, and question routes remain document-scoped.

## File and storage privacy

PDF uploads require a sanitized `.pdf` display filename, accepted PDF media type, `%PDF-` signature, and configured size limit before persistence. Storage ignores the display filename and atomically writes `<PDF_STORAGE_DIR>/uploads/<document-uuid>.pdf`; local development defaults to `backend/storage`, and Railway mounts `/data/documents`. Path resolution cannot leave the uploads root. The uploads directory and PDF/database/key artifacts are gitignored, and the audit found none tracked. PDFs never enter frontend public assets, internal storage keys are absent from response schemas, and missing or invalid files return a fixed response without filesystem details. Extraction logs contain document IDs, page/chunk counts, and status—not lease text.

## Grounding and prompt injection

Gemini's system instruction is separate from the JSON-encoded user question and retrieved lease excerpts. Both are explicitly untrusted data: embedded commands cannot override the task, outside legal knowledge is prohibited, and only supplied evidence may support an answer. Structured output is schema-validated; source IDs are checked twice against retrieved evidence; page/chunk metadata is backend-owned; quotes require source-text containment; malformed output fails safely; and source-less output becomes a fixed abstention. No second LLM or moderation call was added.

## Configuration, CORS, and logs

Database and provider credentials use masked secret settings and are unwrapped only at their client boundaries. `.env` files are gitignored and `.env.example` contains development/example or blank values. Development remains key-optional so mocked tests and non-provider routes work normally. Production startup requires an explicit database URL, both provider keys, an HTTPS non-loopback `FRONTEND_ORIGIN`, disabled debug endpoints, and `PDF_STORAGE_DIR` outside `frontend/public`; error messages name settings without echoing values. Railway `postgresql://` connection strings are normalized to `postgresql+psycopg://` because psycopg 3 is the installed driver.

CORS never accepts a wildcard or origins containing credentials, paths, queries, or fragments. Development allows the primary `http://localhost:3000` plus explicit local fallback origins. Non-development environments ignore the fallback list and allow only `FRONTEND_ORIGIN`.

API responses use fixed errors for storage, database, provider, and unexpected failures; raw provider payloads, filesystem paths, stack traces, and secrets are not returned. Server logs retain document IDs, counts, timings, safe provider status/type/request IDs, and exception traces where needed, while avoiding API keys, prompts, full questions, and lease text.

## Database and cache safety

Chunks and grounded-answer cache rows have required document foreign keys with intentional database and ORM delete cascades. Retrieval, orchestration, cache lookup, cache validation, and re-index invalidation all include `document_id`. Cache reads revalidate cited chunk ownership; cache hits cannot cross documents; re-indexing deletes old answers for that document; and no destructive cleanup endpoint was added. Stage 6B requires no schema migration and preserves existing document/chunk/cache data.

## Remaining production work

There is still no authentication, owner/tenant data model, managed object storage or explicit encryption/retention policy, durable job queue, cross-process rate coordination, OCR, malware scanning, backup/restore automation, or multi-region deployment infrastructure. Prompt controls reduce injection risk but cannot prove semantic faithfulness, and abstention has no calibrated relevance threshold. The application must not be exposed as a multi-user service until authenticated document ownership is implemented at the central access boundary.

The supported portfolio deployment uses one Railway API replica, Railway's pgvector template, an attached `/data/documents` volume, and a Vercel frontend. Alembic runs as a Railway pre-deploy command; Uvicorn binds to Railway's injected `PORT`; `/health` gates activation; production CORS accepts only the final Vercel HTTPS origin. This makes the current single-user demo deployable but does not remove the limitations above.
