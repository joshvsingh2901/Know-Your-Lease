# Know Your Lease

Know Your Lease is a legal document assistant that will answer questions using only a user's uploaded lease and cite the exact supporting clauses. Stage 1 provides the working application foundation: PDF upload transport, metadata persistence, and a polished web interface. It intentionally does not parse or analyze the lease yet.

## Technology stack

- **Frontend:** Next.js, React, TypeScript, Tailwind CSS
- **Backend:** FastAPI, Pydantic, SQLAlchemy, Alembic
- **Database:** PostgreSQL 18 with pgvector
- **Local infrastructure:** Docker Compose

## Repository structure

```text
frontend/                 Next.js application and upload UI
  app/                    App Router pages and global styles
  components/             Interactive UI components
  lib/                    Central API client
  types/                  Shared frontend data types
backend/
  app/api/routes/         FastAPI endpoints
  app/core/               Environment settings and database session
  app/models/             SQLAlchemy entities
  app/schemas/            Pydantic response contracts
  alembic/                Database migrations
  tests/                  Backend API and persistence tests
docs/                     Architecture and project-specific RAG decisions
docker-compose.yml        PostgreSQL + pgvector service
```

## Prerequisites

- Python 3.11 or newer
- Node.js 20.19+, 22.13+, or 24+ (an active LTS release is recommended)
- Docker Desktop or another Docker Engine with Compose

## Environment setup

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

The included defaults are for local development only. `OPENAI_API_KEY` is reserved for a later stage and may remain empty.

## Run locally

Start PostgreSQL and wait for it to become healthy:

```bash
docker compose up -d database
docker compose ps
```

The database is exposed on host port `5433` by default to avoid clashing with a system PostgreSQL installation. Set `POSTGRES_PORT` and update `backend/.env` if you prefer another port.

Apply the schema migration:

```bash
cd backend
source .venv/bin/activate
alembic upgrade head
```

Start FastAPI in that terminal:

```bash
uvicorn app.main:app --reload --port 8000
```

The API is available at `http://localhost:8000`, with interactive documentation at `http://localhost:8000/docs`.

In another terminal, start Next.js:

```bash
cd frontend
npm run dev
```

Open `http://localhost:3000` and upload a PDF lease.

The default command explicitly requires port `3000` so Next.js cannot silently move to a CORS-incompatible origin. If another local project must keep port `3000`, use `npm run dev:3001`; that explicit development origin is also allowed by the backend.

## API

### `GET /health`

Returns `{ "status": "ok" }` without requiring the database.

### `POST /documents`

Accepts one `file` field as `multipart/form-data`. The API validates a `.pdf` filename, PDF media type, `%PDF-` file signature, and the configured size limit. It creates a `documents` metadata record and returns:

```json
{
  "id": "uuid",
  "filename": "lease.pdf",
  "status": "uploaded",
  "created_at": "2026-08-06T12:00:00Z"
}
```

The raw PDF is not permanently saved in Stage 1.

## Verification

Run backend tests and static checks:

```bash
cd backend
source .venv/bin/activate
pytest
ruff check .
alembic check
```

Run frontend checks:

```bash
cd frontend
npm run lint
npm run typecheck
npm run build
```

Validate infrastructure configuration:

```bash
docker compose config --quiet
```

## Current features

- Responsive, accessible PDF selection and drag-and-drop UI
- Loading, success, and human-readable error states
- Centralized frontend API client
- Basic PDF extension, media-type, magic-byte, and size validation
- UUID document metadata persisted through SQLAlchemy
- Alembic-managed schema and pgvector extension setup
- Explicit local CORS configuration
- Isolated tests that do not require OpenAI or external services

## Planned RAG pipeline

```text
PDF extraction
  → page-aware text
  → chunking and source metadata
  → embeddings
  → pgvector storage
  → document-scoped retrieval
  → grounded answer generation
  → page and section citations
```

See [the architecture](docs/architecture.md) and [application RAG decisions](docs/rag-decisions.md) for the reasoning behind the current design.
