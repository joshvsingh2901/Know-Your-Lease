# Know Your Lease

Know Your Lease is a portfolio-quality legal document assistant. Stage 2 accepts a lease PDF, retains it safely, extracts page-aware text, creates retrieval chunks, embeds them with Voyage AI, and stores the resulting index in PostgreSQL with pgvector. Question answering begins in Stage 3.

## Technology stack

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS
- **Backend:** FastAPI, Pydantic, SQLAlchemy, Alembic
- **Ingestion:** PyMuPDF, a local paragraph/sentence-aware chunker, Voyage AI
- **Database:** PostgreSQL 18 with pgvector
- **Local infrastructure:** Docker Compose

## Repository structure

```text
frontend/                    Next.js upload and processing-status UI
backend/
  app/api/routes/            Upload, status, and chunk-inspection endpoints
  app/models/                Document and DocumentChunk entities
  app/services/              Storage, extraction, chunking, embeddings, ingestion
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
- A Voyage AI API key for real document indexing

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
```

`OPENAI_API_KEY` remains reserved for a later answer-generation stage. It is not used for Stage 2. Real `.env` files and `backend/storage/uploads/` are ignored by Git.

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

## Upload and indexing lifecycle

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

## API

- `GET /health` — service health.
- `POST /documents` — validate/store a PDF, create its record, and enqueue in-process ingestion.
- `GET /documents/{document_id}` — current `uploaded | processing | ready | failed` state.
- `GET /documents/{document_id}/chunks?limit=50&offset=0` — paginated development inspection of chunk text and provenance; embeddings are intentionally omitted.

Example inspection after an upload:

```bash
curl http://localhost:8000/documents/DOCUMENT_ID
curl 'http://localhost:8000/documents/DOCUMENT_ID/chunks?limit=10'
```

## Optional real Voyage ingestion test

After the database is running, migrations are current, and `VOYAGE_API_KEY` is set:

```bash
cd backend
source .venv/bin/activate
python scripts/test_ingestion.py /absolute/path/to/small-digital-lease.pdf
```

The command makes real Voyage calls, respects the configured 3 RPM / 10,000 TPM limits, and reports the document ID, final status, chunk count, and page numbers. It is never run by the automated test suite.

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
