# Architecture

The current system is a browser application, a FastAPI service with in-process ingestion, private local development file storage, Voyage AI embeddings, exact PostgreSQL + pgvector retrieval, Gemini grounded answer generation, verified citation snippets, answer reuse, and PDF source inspection. The original upload and indexing boundaries remain intact.

## Current system

```text
Browser / Next.js
  ↓ multipart PDF
FastAPI upload endpoint
  ↓
Safe local PDF storage
  ↓ FastAPI BackgroundTasks
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
- `backend/app/api/document_access.py` is the single route-level document access boundary. It currently exposes all local records; a future authenticated owner predicate belongs there.
- `backend/app/services/storage.py` maps a document UUID to an internal `uploads/<uuid>.pdf` key. Original filenames are metadata only.
- `backend/app/services/pdf_extraction.py`, `text_normalization.py`, and `chunking.py` form an inspectable preprocessing pipeline with no LLM or orchestration framework.
- `backend/app/services/embeddings.py` batches document chunks, applies account-aware pacing and bounded transient retries, and validates Voyage output.
- `backend/app/services/document_ingestion.py` owns status transitions and the final all-or-nothing chunk persistence transaction.
- `backend/app/services/retrieval.py` performs exact cosine search with a mandatory `document_id` predicate, retrieves 10 candidates, and diversifies them to at most 5 results.
- `backend/app/services/generation.py` isolates the official Google GenAI client, structured JSON response schema, grounding prompt, prompt-injection boundary, source-ID validation, abstention behavior, and one bounded retry for transient provider overload.
- `backend/app/services/citation_snippets.py` validates model quotes against source chunks and provides bounded sentence-aware fallback snippets plus conservative heading detection.
- `backend/app/services/question_answering.py` requires a ready document, coordinates query embedding, retrieval, generation, verified snippets, and backend citation mapping.
- `backend/app/models/` contains `Document` and document-owned `DocumentChunk` records.
- `grounded_answer_cache` stores document-scoped, versioned, verified final answers for exact normalized question reuse.
- `backend/alembic/` is the only production schema mechanism; application startup does not create tables.

## Request and processing lifecycle

```text
POST /documents
  ↓ validate filename, media type, %PDF- signature, and size
Persist bytes atomically under a UUID storage key
  ↓
Insert Document(status=uploaded)
  ↓ return 201 and schedule background task
Document(status=processing)
  ↓
Extract pages → normalize → chunk → embed
  ↓ one database transaction
Delete any stale chunks → insert complete new index → status=ready
```

Any extraction, embedding, or persistence failure removes chunk rows for that document and records `failed` plus a short safe message. A `ready` status therefore means that all chunk text, provenance, and vectors were persisted successfully.

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

The original PDF remains in gitignored `backend/storage/uploads/` for future source viewing, outside frontend public assets. UUIDs generate storage keys; original filenames are display metadata only. Storage resolution rejects paths outside the uploads root, API responses never expose internal paths, and missing files return a fixed safe 404. Each chunk and cache row has a required foreign key to exactly one document with intentional delete cascade. Retrieval includes a `document_id` SQL filter before ranking and applies a second defensive scope check in orchestration; there is intentionally no global corpus search design.

`GET /documents` is a lightweight local/single-user library of safe document metadata. The frontend can reopen a ready record without processing it again. Metadata, list, PDF, question, chunk, and retrieval routes all pass through the centralized route access boundary. Browser localStorage remembers only the active UUID and is not an access-control mechanism; production must add an authenticated owner/tenant predicate at that boundary before multi-user deployment. Internal scripts and services operate in a trusted local context and must receive an already-authorized document ID in a future multi-user system.

The vector column has 1024 dimensions to match `voyage-law-2`. Conventional document/page indexes and a unique per-document chunk order support isolation and inspection. There is no ANN index: a normal lease contains few enough chunks that exact cosine distance is simpler and sufficiently fast.

## Grounding and citation boundary

Gemini receives only the final retrieved excerpts, never the complete lease or PDF. Trusted system instructions are separate from a JSON-encoded untrusted question/evidence payload. The system instruction treats both the question and lease excerpts as untrusted data, forbids following embedded commands, outside legal knowledge, and legal advice, and requires supplied `SOURCE_n` identifiers. The provider response is validated against a strict JSON schema. Unknown identifiers reject the response at both generation and orchestration boundaries; duplicate valid identifiers are deduplicated; and a response with no valid citations is replaced by the fixed abstention answer.

Page numbers, section titles, snippets, similarity scores, and chunk IDs are mapped from retrieval results in backend code. A model-provided quote is used only after whitespace-normalized containment validation against its matching chunk. It never controls page metadata, and an invalid quote is replaced by a local relevant-sentence fallback.

`GET /documents/{document_id}/pdf` resolves only the document's already-owned storage key, confirms that the file exists, and serves it as `application/pdf` without exposing the internal path. At ready state, the frontend presents a two-column workspace on desktop: the PDF viewer on the left and the question/answer panel on the right. Citation actions jump the viewer to the cited page, then attempt a whitespace-normalized match against React-PDF's rendered text-layer spans. Only matching spans are highlighted; an imperfect match leaves the correct page visible without a fabricated highlight.

## Processing boundary

FastAPI `BackgroundTasks` keeps the upload request responsive without adding Redis or a worker service. The embedding service is process-local and serializes provider calls so its 3 RPM / 10K TPM pacing applies across uploads handled by that process. This is an MVP execution model: a production deployment should move ingestion to a durable queue because in-flight work is lost if the API process restarts, and rate limiting would need coordination across multiple API processes.

## Production boundaries and current limitations

Provider and database exceptions never flow directly into API responses. Known provider 429 and 5xx failures return safe structured errors distinct from missing or invalid configuration and unexpected provider failures. Logs retain document IDs, counts, timings, provider status/type/request IDs, and stack traces where useful, but omit API keys, raw provider bodies, prompts, and extracted lease text.

Configuration masks database/provider secrets in settings representations. Startup validation keeps development key-optional, while production requires explicit database/provider settings, HTTPS non-loopback frontend origin, disabled debug endpoints, and storage outside `frontend/public`. CORS accepts validated explicit HTTP(S) origins only: configured local origins in development and only `FRONTEND_ORIGIN` outside development. Chunk/retrieval debug endpoints default on only in development and return 404 when disabled.

The current system does not provide authentication/user ownership, encryption policy or managed object storage, OCR, durable background jobs, cross-process rate limiting, chat history, query rewriting, reranking, hybrid/full-text retrieval, coordinate-level PDF highlights, or a calibrated relevance threshold. Text-layer highlighting is best-effort because PDFs can expose text with imperfect spacing. Abstention relies on evidence-limited prompting plus strict source-ID validation, not a calibrated score cutoff or a second faithfulness model. It is not safe for multi-user exposure until authenticated ownership is added centrally.
