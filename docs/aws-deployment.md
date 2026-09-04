# AWS Deployment Preparation

Phase 6 targets an AWS production runtime, but Phase 6A only prepares repository
configuration. No AWS or Vercel resources have been provisioned, no image has been
pushed to ECR, and no deployment has occurred.

## Approved target

- Region: `ca-central-1`
- Frontend: Vercel-hosted Next.js
- Authentication: Cognito managed login with Authorization Code and PKCE
- Public API: internet-facing Application Load Balancer over HTTPS
- Compute: ECS/Fargate tasks in public subnets, with no NAT Gateway
- Database: RDS PostgreSQL with pgvector in isolated subnets
- Documents: private S3 bucket
- Ingestion: SQS main queue with an AWS-managed DLQ redrive policy
- Images: one private ECR repository
- Secrets: Secrets Manager, injected through workload-scoped execution roles

Initial Fargate sizing is deliberately small:

| Workload | Form | CPU | Memory | Desired count |
| --- | --- | ---: | ---: | ---: |
| API | ECS service | 0.25 vCPU | 1 GiB | 1 |
| Worker | ECS service | 0.25 vCPU | 1 GiB | 1 |
| Migration | One-off task | 0.25 vCPU | 1 GiB | Not applicable |

This is a cost-conscious initial deployment, not a highly available design.

## One image, three commands

The existing `backend/Dockerfile` remains the only runtime image:

| Workload | Command |
| --- | --- |
| API | Image default: `uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Worker | `python -m app.workers.ingestion` |
| Worker health check | `python -m app.workers.ingestion --check` |
| Migration | `alembic upgrade head` |

The API validates before importing the FastAPI application, the worker validates
before constructing SQS/S3/database/provider clients, and Alembic validates only
its database setting. ECS must override the image's HTTP health check for the
worker because the Dockerfile health check is API-specific.

## Workload-specific validation

All workloads reuse `Settings`; separate settings classes and duplicate rules are
unnecessary. The entry points are:

- `validate_api_runtime_settings`: database, S3, SQS, Cognito, frontend origin,
  Voyage, Gemini, and production security requirements.
- `validate_worker_runtime_settings`: database, S3, SQS, processing timeout, and
  Voyage requirements. It deliberately does not inspect API-only Cognito, CORS,
  Gemini, or debug settings.
- `validate_migration_runtime_settings`: an explicit database URL in production.

This split is a least-secret boundary. A task receives only the secrets and
non-secret settings needed by the code it executes.

## ECS deployment configuration map

### API service

Non-secret environment:

```dotenv
ENVIRONMENT=production
PORT=8000
DOCUMENT_STORAGE_BACKEND=s3
S3_BUCKET_NAME=<private-pdf-bucket>
AWS_REGION=ca-central-1
INGESTION_MODE=sqs
SQS_INGESTION_QUEUE_URL=<main-ingestion-queue-url>
INGESTION_PROCESSING_TIMEOUT_SECONDS=900
AUTH_MODE=cognito
COGNITO_REGION=ca-central-1
COGNITO_USER_POOL_ID=<user-pool-id>
COGNITO_APP_CLIENT_ID=<public-app-client-id>
FRONTEND_ORIGIN=https://<vercel-production-domain>
DEBUG_ENDPOINTS_ENABLED=false
ANSWER_CACHE_VERSION=v1
```

Secrets Manager values:

```dotenv
DATABASE_URL=<runtime-postgresql-url>
VOYAGE_API_KEY=<secret>
GEMINI_API_KEY=<secret>
```

The API needs Voyage to embed questions and Gemini to generate grounded answers.
Production validation requires S3 and SQS; local storage and inline ingestion are
development-only modes.

### Ingestion worker service

Non-secret environment:

```dotenv
ENVIRONMENT=production
DOCUMENT_STORAGE_BACKEND=s3
S3_BUCKET_NAME=<private-pdf-bucket>
AWS_REGION=ca-central-1
INGESTION_MODE=sqs
SQS_INGESTION_QUEUE_URL=<main-ingestion-queue-url>
INGESTION_PROCESSING_TIMEOUT_SECONDS=900
```

Secrets Manager values:

```dotenv
DATABASE_URL=<runtime-postgresql-url>
VOYAGE_API_KEY=<secret>
```

Chunking, embedding-model, batching, pacing, and retry settings currently have
validated application defaults. They may be overridden on the worker when an
operational decision requires it; they are not mandatory deployment inputs.
The worker does not need `FRONTEND_ORIGIN`, Cognito configuration,
`GEMINI_API_KEY`, or `ANSWER_CACHE_VERSION`.

`python -m app.workers.ingestion --check` performs this validation and exits
without contacting PostgreSQL, SQS, S3, Voyage, Gemini, or Cognito. A successful
check exits zero; invalid settings produce a non-zero process exit without
printing secret values.

### Migration task

The migration task receives only this Secrets Manager value:

```dotenv
DATABASE_URL=<migration-postgresql-url>
```

`alembic upgrade head` imports SQLAlchemy metadata but does not import the FastAPI
application. It therefore does not require S3, SQS, Cognito, frontend, Voyage, or
Gemini configuration. Migrations remain separate from API startup.

### Vercel frontend

These are public build-time configuration, not secrets:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://api.<domain>
NEXT_PUBLIC_COGNITO_DOMAIN=https://<domain>.auth.ca-central-1.amazoncognito.com
NEXT_PUBLIC_COGNITO_APP_CLIENT_ID=<public-app-client-id>
NEXT_PUBLIC_COGNITO_REDIRECT_URI=https://<vercel-production-domain>/auth/callback
```

The Cognito app client must be public and have no client secret.

## Secret and non-secret ownership

Secrets:

- Runtime and migration `DATABASE_URL` values
- `VOYAGE_API_KEY`
- `GEMINI_API_KEY`

Non-secret configuration:

- AWS region, bucket name, and queue URL
- Cognito pool and public app-client identifiers
- Cognito managed-login domain
- Exact frontend and API origins
- Runtime mode, processing timeout, and answer-cache version

AWS credentials are never application configuration. ECS supplies them through
separate API and worker task roles. Secret retrieval belongs to narrowly scoped
task execution roles.

## Phase boundary

Phase 6A does not create the VPC, subnets, ALB, ECS cluster, ECR repository, RDS
instance, S3 bucket, SQS/DLQ, Cognito pool, IAM roles, Secrets Manager entries, or
Vercel deployment. Those actions remain pending; Phase 6B has not started.
