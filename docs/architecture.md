# Architecture

Stage 2 is a browser application, a FastAPI service with in-process ingestion, local development file storage, Voyage AI embeddings, and PostgreSQL + pgvector.

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
```

- `frontend/` owns file selection, upload feedback, and polling. It stops polling when the document becomes `ready` or `failed`.
- `backend/app/api/routes/documents.py` owns upload validation and the document/status/debug contracts.
- `backend/app/services/storage.py` maps a document UUID to an internal `uploads/<uuid>.pdf` key. Original filenames are metadata only.
- `backend/app/services/pdf_extraction.py`, `text_normalization.py`, and `chunking.py` form an inspectable preprocessing pipeline with no LLM or orchestration framework.
- `backend/app/services/embeddings.py` batches document chunks, applies account-aware pacing and bounded transient retries, and validates Voyage output.
- `backend/app/services/document_ingestion.py` owns status transitions and the final all-or-nothing chunk persistence transaction.
- `backend/app/models/` contains `Document` and document-owned `DocumentChunk` records.
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

## Persistence and isolation

The original PDF remains in `backend/storage/uploads/` for future source viewing. API responses never expose its internal path. Each chunk has a required foreign key to exactly one document, and the foreign key cascades on document deletion. Stage 3 retrieval must always include a `document_id` filter; there is intentionally no global corpus search design.

The vector column has 1024 dimensions to match `voyage-law-2`. Stage 2 adds conventional document/page indexes and a unique per-document chunk order, but no ANN index. A normal lease contains few enough chunks that exact similarity search will be simpler and sufficiently fast when Stage 3 adds retrieval.

## Processing boundary

FastAPI `BackgroundTasks` keeps the upload request responsive without adding Redis or a worker service. The embedding service is process-local and serializes provider calls so its 3 RPM / 10K TPM pacing applies across uploads handled by that process. This is an MVP execution model: a production deployment should move ingestion to a durable queue because in-flight work is lost if the API process restarts, and rate limiting would need coordination across multiple API processes.

## Not implemented

Stage 2 does not provide OCR, question embeddings, vector search, reranking, answer generation, chat history, or citations in generated answers. The chunks endpoint exists only to inspect the index during development.
