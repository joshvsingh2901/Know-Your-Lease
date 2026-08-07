# Production Hardening

## Reuse and local library

Documents are durable backend records. Uploading persists a UUID-owned PDF, its chunks, and a ready status; reopening a listed ready document, refreshing the browser, and asking later questions reuse those records without extraction or document embeddings. The browser stores only the active UUID in localStorage for convenience. It is not an authorization boundary.

`GET /documents` is a deliberately small single-user/local library API. It returns safe metadata only and the frontend presents ready documents as compact reopen buttons beside upload. A future authenticated deployment must add an owner/tenant scope and enforce it centrally across list, metadata, PDF, question, cache, and debug routes. No fake ownership field or localStorage-based access control exists today.

## Answer reuse

`grounded_answer_cache` stores a final answer and already-verified citation payload only after a successful grounded response with at least one citation. Its unique key is document UUID, whitespace/case-normalized exact question, and `ANSWER_CACHE_VERSION`. The same exact normalized question therefore skips Voyage and Gemini on later requests; paraphrases do not collide. Semantic caching was deliberately excluded because superficially similar legal questions can differ materially, and no labeled data supports a safe similarity threshold. Provider failures, empty-evidence results, and abstentions are not cached. Cache reads revalidate cited chunk IDs against the requested document; document deletion cascades cache deletion, re-indexing invalidates that document's prior answers, and a version bump invalidates entries after material prompt or response-format changes.

## Provider and debug boundaries

Question failures use safe structured API errors. A known 429 returns `provider_rate_limited`; a known upstream 5xx returns `provider_temporarily_unavailable`; missing or invalid configuration returns `provider_configuration`; other provider failures return `provider_request_failed`. Provider payloads, keys, and stack traces never reach the browser. Existing bounded retries remain the only automatic retries.

Chunk inspection and retrieval diagnostics are enabled by default only when `ENVIRONMENT=development`. Set `DEBUG_ENDPOINTS_ENABLED=true` deliberately for a non-development diagnostic environment; otherwise `/chunks` and `/retrieve` return 404. Normal document metadata, PDF, and question routes remain document-scoped.

## Privacy and remaining production work

PDFs remain outside frontend public assets under generated UUID storage keys. Filenames are metadata only, uploads require a PDF extension/content type/signature and obey the configured size cap, and unavailable files return a safe 404 without storage paths. Extraction and provider logs avoid lease contents.

There is still no authentication, durable job queue, cross-process rate coordination, object storage, OCR, or deployment configuration. Production must set a real `FRONTEND_ORIGIN`; CORS never uses a wildcard. It must also provide authenticated ownership and protect all document routes before exposing this application to multiple users.
