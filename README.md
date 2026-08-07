# Know Your Lease

Know Your Lease is a portfolio-quality legal document assistant. It accepts a lease PDF, retains it safely, extracts page-aware text, indexes retrieval chunks with Voyage AI and pgvector, and answers questions using only retrieved lease evidence. Stage 4 adds concise verified citations and side-by-side source inspection.

## Technology stack

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS
- **Backend:** FastAPI, Pydantic, SQLAlchemy, Alembic
- **Ingestion:** PyMuPDF, a local paragraph/sentence-aware chunker, Voyage AI
- **RAG:** Voyage query embeddings, exact pgvector cosine search, Gemini structured generation
- **Database:** PostgreSQL 18 with pgvector
- **Local infrastructure:** Docker Compose

## Repository structure

```text
frontend/                    Next.js upload, questions, PDF viewer, and citation UI
backend/
  app/api/routes/            Document, retrieval, and question endpoints
  app/models/                Document and DocumentChunk entities
  app/services/              Ingestion, retrieval, grounded-generation services
  alembic/                   Database migrations
  scripts/test_ingestion.py  Optional real Voyage smoke test
  storage/uploads/           Ignored local PDF storage
  tests/                     Mocked, offline automated tests
docs/                        Architecture and RAG decision record
```

## Prerequisites

- Python 3.11+
- Node.js 20.19+, 22.13+, or 24+
- Docker Desktop or another Docker Engine with Compose
- A Voyage AI API key for real document indexing and question embeddings
- A Google Gemini API key for grounded answers

## Setup

From the repository root:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local

python3 -m venv backend/.venv
source backend/.venv/bin/activate
python -m pip install -r backend/requirements-dev.txt

cd frontend
npm install
cd ..
```

Set these values in `backend/.env`:

```dotenv
VOYAGE_API_KEY=your-key-here
VOYAGE_EMBEDDING_MODEL=voyage-law-2
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-3.5-flash
```

Optional generation settings are `GEMINI_MAX_OUTPUT_TOKENS=2048`, `GEMINI_THINKING_LEVEL=low`, `GEMINI_MAX_RETRIES=1`, and `GEMINI_RETRY_BASE_SECONDS=2`. Real `.env` files and `backend/storage/uploads/` are ignored by Git. No provider key is exposed to the browser.

## Run locally

Start PostgreSQL and apply the migrations:

```bash
docker compose up -d database
docker compose ps
cd backend
source .venv/bin/activate
alembic upgrade head
```

Start FastAPI:

```bash
uvicorn app.main:app --reload --port 8000
```

In another terminal, start Next.js:

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000`. If port 3000 is occupied, use `npm run dev:3001`; both explicit local origins are permitted in development.

## Upload, indexing, and question lifecycle

```text
POST PDF
  → validate and store under backend/storage/uploads/<document-id>.pdf
  → uploaded
  → background processing
  → page-aware extraction and normalization
  → page-scoped chunks
  → batched Voyage embeddings
  → PostgreSQL DocumentChunk rows with pgvector vectors
  → ready (or failed with a safe error message)
```

The frontend polls document status until `ready` or `failed`. PDFs with little or no extractable text fail clearly because OCR is not implemented yet.

Once the document is ready:

```text
Question
  → one Voyage voyage-law-2 embedding with input_type=query
  → exact cosine search over chunks filtered by document_id
  → 10 candidates, diversified to at most 5 evidence chunks
  → Gemini receives only those excerpts as untrusted evidence
  → structured answer plus SOURCE_n identifiers and supporting quotes
  → backend verifies each quote against its retrieval chunk
  → bounded local fallback excerpt when a quote is invalid or omitted
  → answer with concise source snippets and PDF page navigation
```

Gemini never receives the entire PDF and never supplies trusted page numbers. If its structured response contains no supporting source IDs, the backend returns a fixed abstention instead of an unsupported answer; an unknown source ID rejects the response safely.

The full chunk is retained for retrieval only. Citation cards show a short verified quote or a deterministic sentence-based fallback, rather than the entire chunk. Selecting **View in lease** moves the PDF viewer to the cited page.

## API

- `GET /health` — service health.
- `POST /documents` — validate/store a PDF, create its record, and enqueue in-process ingestion.
- `GET /documents/{document_id}` — current `uploaded | processing | ready | failed` state.
- `GET /documents/{document_id}/pdf` — serve the original document as `application/pdf` for the in-app viewer.
- `GET /documents/{document_id}/chunks?limit=50&offset=0` — paginated development inspection of chunk text and provenance; embeddings are intentionally omitted.
- `POST /documents/{document_id}/retrieve` — development retrieval inspection without Gemini generation.
- `POST /documents/{document_id}/questions` — answer one question using retrieved evidence and return backend-owned citations.

Example inspection after an upload:

```bash
curl http://localhost:8000/documents/DOCUMENT_ID
curl -I http://localhost:8000/documents/DOCUMENT_ID/pdf
curl 'http://localhost:8000/documents/DOCUMENT_ID/chunks?limit=10'
curl -X POST http://localhost:8000/documents/DOCUMENT_ID/retrieve \
  -H 'Content-Type: application/json' \
  -d '{"question":"Can I have pets?"}'
curl -X POST http://localhost:8000/documents/DOCUMENT_ID/questions \
  -H 'Content-Type: application/json' \
  -d '{"question":"Can I have pets?"}'
```

Question request strings are limited to 1–1,000 characters and cannot be blank. Questions are accepted only for `ready` documents. The debug retrieval response and answer citations include text, page metadata, and similarity scores, but never embedding arrays.

## Optional real Voyage ingestion test

After the database is running, migrations are current, and `VOYAGE_API_KEY` is set:

```bash
cd backend
source .venv/bin/activate
python scripts/test_ingestion.py /absolute/path/to/small-digital-lease.pdf
```

The command makes real Voyage calls, respects the configured 3 RPM / 10,000 TPM limits, and reports the document ID, final status, chunk count, and page numbers. It is never run by the automated test suite.

## Current limitations

- Scanned/image-only leases need OCR, which is not implemented.
- Ingestion runs in-process rather than through a durable worker queue.
- Rate-limit coordination is process-local, so a multi-process deployment needs shared coordination.
- Authentication and user ownership are not implemented; retrieval is nevertheless always scoped to one document ID.
- Questions are independent: there is no chat history or follow-up rewriting.
- Retrieval uses an exact vector baseline without reranking or hybrid/full-text search.
- Citation cards use short verified excerpts. The PDF text layer highlights them when a normalized text match succeeds; imperfect PDF text layers fall back safely to page navigation.

## Verification

```bash
cd backend
source .venv/bin/activate
ruff check .
pytest -q
alembic upgrade head
alembic check
python -c "from app.main import app; print(app.version)"

cd ../frontend
npm run lint
npm run typecheck
npm run build

cd ..
docker compose config --quiet
```

See [the architecture](docs/architecture.md) and [the RAG decisions](docs/rag-decisions.md) for the implemented design and its current tradeoffs.
