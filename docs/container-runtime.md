# Backend Container Runtime

Phase 1 provides one production-oriented FastAPI image for local Docker use and later reuse by API, migration, and ingestion-worker tasks. It does not deploy AWS infrastructure.

## Build and run locally

Build the image directly from the deliberately narrow backend context:

```bash
docker build -t know-your-lease-api:phase1 backend
```

The easiest complete local backend flow uses Compose. Migrations remain an explicit one-off command:

```bash
cp backend/.env.example backend/.env  # if it does not already exist
docker compose up -d database
docker compose build api
docker compose run --rm api alembic upgrade head
docker compose up -d api
curl http://localhost:8000/health
```

Set `BACKEND_PORT` to change the host port. The container listens on `PORT` (default `8000`) and always binds Uvicorn to `0.0.0.0`. Native frontend development remains unchanged with `cd frontend && npm run dev`. Native backend development also remains available; `docker compose up -d database` still starts only PostgreSQL when named explicitly.

For a standalone container, provide a PostgreSQL URL reachable from that container and a writable storage volume:

```bash
docker run --rm --name know-your-lease-api \
  --env-file backend/.env \
  -e PORT=8080 \
  -e DATABASE_URL=postgresql+psycopg://user:password@database-host:5432/leases \
  -e PDF_STORAGE_DIR=/app/storage \
  -p 8080:8080 \
  -v know-your-lease-pdfs:/app/storage \
  know-your-lease-api:phase1
```

## Runtime configuration

Configuration is supplied only at runtime. No `.env` file or secret is copied into the image. Production requires:

- `ENVIRONMENT=production`
- `DATABASE_URL` for PostgreSQL with pgvector
- `FRONTEND_ORIGIN` as the exact public HTTPS frontend origin
- `VOYAGE_API_KEY` and `GEMINI_API_KEY`
- `DEBUG_ENDPOINTS_ENABLED=false`
- explicit `INGESTION_MODE=inline|sqs`
- explicit `DOCUMENT_STORAGE_BACKEND=local|s3`

`DOCUMENT_STORAGE_BACKEND=local` uses `PDF_STORAGE_DIR` as the writable PDF root (the image default resolves to `/app/storage`). `DOCUMENT_STORAGE_BACKEND=s3` instead requires `S3_BUCKET_NAME` and `AWS_REGION`; boto3 resolves credentials at runtime, so none are copied into the image. `PORT`, model names, upload limits, provider pacing, answer-cache version, and the other existing settings remain environment-configurable. Development and tests may omit provider keys when calls are mocked or those features are unused.

The runtime user is the unprivileged numeric UID/GID `10001:10001`. Only `/app/storage` is prepared as application-writable; application code and dependencies remain read-only to that user. Mount a volume at the configured storage path when PDFs must survive container replacement.

## Health and migrations

Docker checks `GET /health` using Python's standard library, so no `curl` package is added. The endpoint is intentionally a shallow application liveness/configuration check. It does not contact PostgreSQL, Voyage, Gemini, a lease, or ingestion; database readiness is enforced by the migration task and deployment orchestration rather than making transient database failures restart otherwise healthy API processes.

The image contains Alembic and all migrations. Run migrations separately:

```bash
docker run --rm --env-file <production-env-file> \
  know-your-lease-api:phase1 alembic upgrade head
```

Do not put `alembic upgrade head` in the image startup command. With multiple replicas, simultaneous startup migrations can contend or race. The intended production sequence is:

```text
one migration task -> successful alembic upgrade head -> deploy API tasks
```

The same image supports the default Uvicorn API command and the Phase 3A worker override:

```bash
python -m app.workers.ingestion
```

Use `python -m app.workers.ingestion --check` for an offline configuration/startup check. A worker container must disable or replace the image's API `/health` Docker health check because it does not expose HTTP. ECR/ECS resources are not provisioned by this repository.

## Image design

The image uses a digest-pinned `python:3.13.5-slim-bookworm`, matching the repository Python pin. `requirements.txt` retains compatible dependency policy while `requirements.lock` constrains the production resolution to exact versions, including Linux-specific dependencies; the build also runs `pip check`. Plain Uvicorn is retained because ECS/Fargate can scale one process per task; Gunicorn would add process management that this baseline does not need.

The backend `.dockerignore` excludes secrets, virtual environments, caches, tests, evaluations, local PDFs/storage, database artifacts, and editor files. The image copies only dependency manifests, application source, Alembic configuration, and migrations.
