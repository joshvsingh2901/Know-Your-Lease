# Deployment Runbook: Railway + Vercel

This runbook prepares the existing single-user application for one Railway API instance, Railway PostgreSQL with pgvector, a Railway persistent PDF volume, and a Vercel frontend. It does not add authentication; use only non-sensitive demonstration documents until authenticated ownership exists.

## Target topology

```text
Vercel Next.js
  └─ NEXT_PUBLIC_API_BASE_URL=https://<backend>.up.railway.app
       ↓ HTTPS + explicit CORS origin
Railway FastAPI (one replica)
  ├─ DATABASE_URL → Railway pgvector PostgreSQL private URL
  ├─ PDF_STORAGE_DIR=/data/documents
  └─ persistent volume mounted at /data/documents
```

## Railway database

Use Railway's **Postgres with pgvector** template. Railway's standard PostgreSQL image does not include pgvector. Name the service `Postgres` if you want to use the variable reference shown below.

Migration `20260806_0001` executes `CREATE EXTENSION IF NOT EXISTS vector` before creating application tables. Do not create tables manually and never reset the database. The backend pre-deploy command runs the additive chain:

```bash
alembic upgrade head
```

Set backend `DATABASE_URL` to the private service reference:

```text
${{Postgres.DATABASE_URL}}
```

Railway supplies a `postgresql://` URL. The backend converts only that scheme to `postgresql+psycopg://` so SQLAlchemy uses the installed psycopg 3 driver; credentials and the remainder of the URL are unchanged.

## Railway backend service

Connect the GitHub repository to one Railway service and configure:

| Setting | Exact value |
| --- | --- |
| Root Directory | `/backend` |
| Config file path | `/railway.toml` |
| Builder | Railpack |
| Build command | Leave blank; Railpack installs `requirements.txt` |
| Pre-deploy command | `alembic upgrade head` |
| Start command | `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Healthcheck path | `/health` |
| Healthcheck timeout | `120` seconds |
| Replicas | `1` |

The commands and health settings are committed in `railway.toml`. Railway injects `PORT`; do not define it yourself. Python is pinned by `backend/.python-version`.

### Backend environment variables

Configure these on the Railway API service:

```dotenv
ENVIRONMENT=production
DATABASE_URL=${{Postgres.DATABASE_URL}}
FRONTEND_ORIGIN=https://<your-vercel-production-domain>
INGESTION_MODE=inline
DOCUMENT_STORAGE_BACKEND=local
VOYAGE_API_KEY=<secret>
VOYAGE_EMBEDDING_MODEL=voyage-law-2
GEMINI_API_KEY=<secret>
GEMINI_MODEL=gemini-3.5-flash
PDF_STORAGE_DIR=/data/documents
DEBUG_ENDPOINTS_ENABLED=false
ANSWER_CACHE_VERSION=v1
```

`FRONTEND_ORIGIN` must be the exact HTTPS origin with no path or trailing wildcard. Do not set `ADDITIONAL_FRONTEND_ORIGINS` in production. `PORT` and Railway volume variables are platform-provided.

Optional settings can retain their code defaults, including the 20 MB upload limit, Voyage pacing, Gemini output/retry limits, and chunk parameters.

## Railway persistent PDF volume

Attach a volume to the **backend API service**, not the database service.

Use this exact mount path:

```text
/data/documents
```

Set `PDF_STORAGE_DIR=/data/documents`. The application creates and uses `/data/documents/uploads/<document-uuid>.pdf` at runtime. The volume is not required during build or Alembic pre-deploy because migrations do not access PDF files.

Keep one API replica in this legacy Railway `INGESTION_MODE=inline` path: ingestion coordination is process-local, and a Railway service with a volume is not a horizontally shared filesystem. Configure Railway volume backups and capacity monitoring before storing anything important.

This runbook deliberately retains the existing local-volume/inline backend. An AWS-oriented production runtime should set `DOCUMENT_STORAGE_BACKEND=s3`, `INGESTION_MODE=sqs`, the bucket and queue URLs, and `AWS_REGION`, omit the PDF volume, and supply credentials through the platform credential chain. Future ECS tasks should use separate API and worker task roles; this repository does not provision that runtime. See [document storage](document-storage.md) and [SQS ingestion worker](ingestion-worker.md).

## Vercel frontend

Import the same GitHub repository as a Vercel project:

| Setting | Exact value |
| --- | --- |
| Root Directory | `frontend` |
| Framework Preset | Next.js |
| Install Command | Default (`npm install`) |
| Build Command | `npm run build` |
| Output Directory | Default Next.js output |
| Node.js version | `24.x` |

Set this Production environment variable before the final build:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://<your-railway-backend-domain>
```

Do not include a trailing slash. `NEXT_PUBLIC_` values are embedded into the browser bundle at build time, so redeploy Vercel whenever this URL changes. Preview deployment domains are intentionally not accepted by the production API unless a separate preview backend is configured with that exact origin.

## CORS wiring

The two values must describe opposite sides of the same connection:

```text
Railway: FRONTEND_ORIGIN=https://know-your-lease.vercel.app
Vercel:  NEXT_PUBLIC_API_BASE_URL=https://know-your-lease-api.up.railway.app
```

Do not use `*`, comma-separated production origins, a URL path, or an `http://` production frontend origin. Production startup fails closed on unsafe values.

## Deployment order

1. Push the reviewed commit to the public GitHub repository.
2. In Railway, create a project and deploy the **Postgres with pgvector** template; name it `Postgres`.
3. Create the Railway backend service from the GitHub repository, set Root Directory `/backend`, and confirm config path `/railway.toml`.
4. Attach a backend volume at `/data/documents`.
5. Add all Railway environment variables. If the final Vercel domain is not known yet, create/name the Vercel project first and use its stable production domain.
6. Deploy Railway. Confirm the pre-deploy migration succeeds, then generate a public HTTPS domain.
7. Verify `https://<railway-domain>/health` returns `{"status":"ok"}`.
8. In Vercel, import the repository with Root Directory `frontend`, set `NEXT_PUBLIC_API_BASE_URL` to the Railway HTTPS domain, and deploy Production.
9. Confirm Railway `FRONTEND_ORIGIN` exactly matches the final Vercel production origin; redeploy Railway if it changed.
10. Verify the Vercel UI can list documents, upload a disposable non-sensitive PDF, reach `ready`, ask a question, open a citation, and reopen the same document.
11. Verify production debug endpoints return 404.
12. Enable Railway database backups and volume backups, then monitor provider limits and disk capacity.

Railway pre-deploy commands run with service environment variables and private networking, and block a deployment if migration fails. Railway volumes mount only at runtime, which is compatible because only the running API reads/writes PDFs. See Railway's official [pre-deploy](https://docs.railway.com/deployments/pre-deploy-command), [volume](https://docs.railway.com/volumes), [healthcheck](https://docs.railway.com/deployments/healthchecks), and [pgvector guide](https://docs.railway.com/guides/rag-pipeline-pgvector), plus Vercel's [monorepo setup](https://vercel.com/docs/monorepos).
