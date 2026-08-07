# Architecture

Know Your Lease is split into a browser application, an HTTP API, and a relational database. Stage 1 deliberately ends at validated upload transport and metadata persistence; the PDF bytes are not retained or analyzed.

## Current system

```text
Browser
  ↓ multipart PDF upload
Next.js + TypeScript + Tailwind CSS
  ↓ HTTP
FastAPI + Pydantic
  ↓ SQLAlchemy
PostgreSQL 18 + pgvector
```

- `frontend/` owns presentation, local file selection, client-side feedback, and calls to the API through one small client module.
- `backend/app/api/` owns the HTTP contract. The upload endpoint validates the filename, media type, PDF magic bytes, and size before creating metadata.
- `backend/app/models/` owns persisted entities. Stage 1 has only `documents`.
- `backend/alembic/` is the sole production schema migration mechanism. Application startup does not call `create_all()`.
- PostgreSQL runs locally through Docker Compose. The first migration enables the `vector` extension so the database is ready for later embedding storage.

The frontend and backend are separate development processes. CORS permits the configured frontend origin only (`http://localhost:3000` by default), rather than every origin.

## Upload request lifecycle

```text
Select or drop PDF
  ↓
POST /documents
  ↓
Validate extension + media type + %PDF- signature + size
  ↓
Insert Document metadata
  ↓
Return UUID, filename, status, and creation time
```

The uploaded file is closed after validation and is not written to application storage. This minimizes data handling until the ingestion lifecycle is designed in Stage 2.

## Planned RAG flow

```text
PDF
  ↓
Page-aware text extraction
  ↓
Chunking + source metadata
  ↓
Embeddings
  ↓
PostgreSQL + pgvector
  ↓ document-scoped retrieval
Relevant lease passages
  ↓
Grounded LLM generation
  ↓
Answer + page/section citations
```

Stage 2 will add a processing lifecycle and `document_chunks` storage. The API, model, and service boundaries are intentionally small so those additions can be made without replacing the Stage 1 foundation.
