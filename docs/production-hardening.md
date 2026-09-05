# Production Hardening

## Authentication and ownership

Every document-scoped route requires `require_current_user`: a verified Cognito access token resolved/just-in-time-provisioned to a local `users` row (`AUTH_MODE=cognito`), or a fixed local-development user (`AUTH_MODE=disabled`, the local/test default). Production startup rejects `AUTH_MODE=disabled` and an unset `AUTH_MODE` outright.

`backend/app/api/document_access.py` is the single shared access seam used by list, metadata, PDF, question, cache entry points, chunks, and retrieval routes; none of them queries `Document` independently. It resolves a document only when `Document.owner_id` matches the authenticated user's ID, so a document that does not exist and one owned by someone else are indistinguishable: both return 404, never 403, which avoids turning the endpoint into an existence oracle for document UUIDs. A document with a null `owner_id` (a pre-authentication legacy row) matches no user and stays inaccessible until explicitly assigned by the local backfill script. Upload sets `owner_id` from the authenticated user only; a request cannot set or override it.

The SQS ingestion message and the standalone worker are unchanged by this: the worker loads the document by ID from PostgreSQL and never receives, needs, or trusts an owner field. Ownership is enforced once, on the read/write side in `document_access.py`, not duplicated into the queue contract.

## Reuse and local library

Documents are durable backend records. Uploading persists a UUID-owned PDF, its chunks, and a ready status; reopening a listed ready document, refreshing the browser, and asking later questions reuse those records without extraction or document embeddings. The browser stores only the active UUID in localStorage for convenience; it is never an authorization boundary; the backend re-checks ownership on every request. A 404 from a stale or cross-user ID clears the stored ID; a 401 (expired/invalid session) does not, since the ID itself may still be valid once the user signs in again.

`GET /documents` returns only documents owned by the authenticated caller, filtered in the database query itself (`WHERE owner_id = :current_user_id`), not by filtering a full result set after the fact.

## Answer reuse

`grounded_answer_cache` stores a final answer and already-verified citation payload only after a successful grounded response with at least one citation. Its unique key is document UUID, whitespace/case-normalized exact question, and `ANSWER_CACHE_VERSION`. The same exact normalized question therefore skips Voyage and Gemini on later requests; paraphrases do not collide. Semantic caching was deliberately excluded because superficially similar legal questions can differ materially, and no labeled data supports a safe similarity threshold. Provider failures, empty-evidence results, and abstentions are not cached. Cache reads revalidate cited chunk IDs against the requested document; document deletion cascades cache deletion, re-indexing invalidates that document's prior answers, and a version bump invalidates entries after material prompt or response-format changes. The cache key remains document ID + normalized question + version, with no added `owner_id`: document IDs are globally unique, and every read path reaches the cache only after the access seam has already confirmed the caller owns that document, so a cache hit is unreachable by anyone else.

## Provider and debug boundaries

Question failures use safe structured API errors. A known 429 returns `provider_rate_limited`; a known upstream 5xx returns `provider_temporarily_unavailable`; missing or invalid configuration returns `provider_configuration`; other provider failures return `provider_request_failed`. Provider payloads, keys, and stack traces never reach the browser. Existing bounded retries remain the only automatic retries.

Chunk inspection and retrieval diagnostics are enabled by default only when `ENVIRONMENT=development`. Set `DEBUG_ENDPOINTS_ENABLED=true` deliberately for a non-development diagnostic environment; otherwise `/chunks` and `/retrieve` return 404. Normal document metadata, PDF, and question routes remain document-scoped.

## File and storage privacy

PDF uploads require a sanitized `.pdf` display filename, accepted PDF media type, `%PDF-` signature, and configured size limit before persistence. Storage ignores the display filename and uses `uploads/<document-uuid>.pdf` through a local-or-S3 `DocumentStorage` interface. Local writes are atomic and traversal-resistant; S3 objects use SSE-S3, no ACL, and direct key access without listing or public URLs. The uploads directory and PDF/database/key artifacts are gitignored. PDFs never enter frontend public assets, internal storage keys and bucket details are absent from response schemas, and missing or provider-failed reads return fixed safe responses. Extraction logs contain document IDs, page/chunk counts, and status—not lease text.

## Grounding and prompt injection

Gemini's system instruction is separate from the JSON-encoded user question and retrieved lease excerpts. Both are explicitly untrusted data: embedded commands cannot override the task, outside legal knowledge is prohibited, and only supplied evidence may support an answer. Structured output is schema-validated; source IDs are checked twice against retrieved evidence; page/chunk metadata is backend-owned; quotes require source-text containment; malformed output fails safely; and source-less output becomes a fixed abstention. No second LLM or moderation call was added.

## Configuration, CORS, and logs

Database and provider credentials use masked secret settings and are unwrapped only at their client boundaries. `.env` files are gitignored and `.env.example` contains development/example, blank, or placeholder values. Development remains key-optional so mocked tests and non-provider routes work normally.

Production validation is workload-specific. The API requires an explicit database URL, `DOCUMENT_STORAGE_BACKEND=s3`, its bucket and region, `INGESTION_MODE=sqs`, its queue URL, `AUTH_MODE=cognito` with pool/client configuration, both provider keys, an HTTPS non-loopback `FRONTEND_ORIGIN`, and disabled debug endpoints. The ingestion worker requires only an explicit database URL, S3, SQS, the bounded processing timeout, and Voyage; it does not validate or receive Cognito, frontend, Gemini, or API debug configuration. Alembic requires only an explicit production database URL. Common database, storage, and queue checks are reused rather than duplicated.

This split implements least-secret exposure for the planned ECS execution roles. AWS credentials are not application settings: boto3 uses profiles/environment credentials locally and ECS task-role credentials in AWS. `postgresql://` connection strings are normalized to `postgresql+psycopg://` because psycopg 3 is the installed driver.

CORS never accepts a wildcard or origins containing credentials, paths, queries, or fragments. Development allows the primary `http://localhost:3000` plus explicit local fallback origins. Non-development environments ignore the fallback list and allow only `FRONTEND_ORIGIN`. `allow_headers` includes `Authorization` for bearer tokens; `allow_credentials` is `False` since the API does not use cookies.

API responses use fixed errors for storage, database, provider, and unexpected failures; raw provider payloads, filesystem paths, stack traces, and secrets are not returned. A missing, malformed, expired, wrong-issuer, or wrong-client token returns a generic `401 Not authenticated.` with a `WWW-Authenticate: Bearer` header; it never echoes the token, the Cognito subject, the issuer, the client ID, or a JWKS/signature parse reason. A JWKS fetch failure returns `503`, not `401`, since it is a provider-availability fault rather than a bad credential. Server logs retain document IDs, counts, timings, safe provider status/type/request IDs, and exception traces where needed, while avoiding API keys, prompts, full questions, lease text, raw tokens, and token claims.

## Database and cache safety

Chunks and grounded-answer cache rows have required document foreign keys with intentional database and ORM delete cascades. `documents.owner_id` is a nullable foreign key to `users.id` (`ON DELETE CASCADE`); it stays nullable in the schema so a database can hold pre-authentication rows without violating a constraint, while the access seam treats a null owner as accessible to no one. Retrieval, orchestration, cache lookup, cache validation, and re-index invalidation all include `document_id`. Cache reads revalidate cited chunk ownership; cache hits cannot cross documents; re-indexing deletes old answers for that document; and no destructive cleanup endpoint was added. Migration `20260904_0006` is additive only (new `users` table, new nullable `documents.owner_id`) and preserves existing document/chunk/cache data; a separate backfill script assigns ownerless local-development rows to one fixed user and refuses to run when `ENVIRONMENT=production`.

## Remaining production work

Phase 4 implements Cognito JWT verification, local user provisioning, and per-document ownership enforcement in application code. Phase 6B provisioned the temporary VPC/data plane (private RDS, S3, SQS/DLQ), and Phase 6C provisioned a non-root deployment identity, a live Cognito user pool and public app client, a private ECR repository, the Voyage/Gemini application secrets, and the ECS execution/task IAM roles (see [aws-identity.md](aws-identity.md) and [aws-resource-inventory.md](aws-resource-inventory.md)). No ECS cluster/service/task, ALB, DNS resource, or Vercel deployment exists yet, so no traffic actually flows through this stack: the API is not deployed, the app client's callback URLs are `localhost` only, and the `database-url-app`/`database-url-migrate` secrets do not exist until an in-VPC task creates the corresponding PostgreSQL roles. Pgvector is not active until that migration task executes and verifies the base migration inside the VPC. Automated DLQ replay, visibility heartbeats, cross-process rate coordination, OCR, malware scanning, restore automation, multi-region infrastructure, and re-ingestion remain later work. Prompt controls reduce injection risk but cannot prove semantic faithfulness, and abstention has no calibrated relevance threshold.
