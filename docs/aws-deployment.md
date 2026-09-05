# AWS Deployment Preparation

Phase 6 targets an AWS production runtime. Phase 6A prepared repository
configuration, Phase 6B provisioned the network/data-plane foundation, and Phase 6C
provisioned a non-root deployment identity, a live Cognito user pool, a private ECR
repository, two application secrets, and the ECS execution/task IAM roles -- all
recorded in [the resource inventory](aws-resource-inventory.md) and
[the identity runbook](aws-identity.md). No image has been pushed to ECR, no ECS
cluster/service/task exists, and no application or Vercel deployment has occurred.

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
S3_BUCKET_NAME=know-your-lease-prod-297784246437-ca-central-1
AWS_REGION=ca-central-1
INGESTION_MODE=sqs
SQS_INGESTION_QUEUE_URL=https://sqs.ca-central-1.amazonaws.com/297784246437/know-your-lease-ingestion-prod
INGESTION_PROCESSING_TIMEOUT_SECONDS=900
AUTH_MODE=cognito
COGNITO_REGION=ca-central-1
COGNITO_USER_POOL_ID=ca-central-1_Lhw9u8Yh6
COGNITO_APP_CLIENT_ID=4sq1r3l1flfv1acrkrqc69aoh9
FRONTEND_ORIGIN=https://<vercel-production-domain>
DEBUG_ENDPOINTS_ENABLED=false
ANSWER_CACHE_VERSION=v1
```

Secrets Manager values (execution role: `kyl-api-execution`):

```dotenv
DATABASE_URL=<runtime-postgresql-url>          # created in Phase 6D: know-your-lease/prod/database-url-app
VOYAGE_API_KEY=<secret>                        # know-your-lease/prod/voyage-api-key (created Phase 6C)
GEMINI_API_KEY=<secret>                        # know-your-lease/prod/gemini-api-key (created Phase 6C)
```

The API needs Voyage to embed questions and Gemini to generate grounded answers.
Production validation requires S3 and SQS; local storage and inline ingestion are
development-only modes.

### Ingestion worker service

Non-secret environment:

```dotenv
ENVIRONMENT=production
DOCUMENT_STORAGE_BACKEND=s3
S3_BUCKET_NAME=know-your-lease-prod-297784246437-ca-central-1
AWS_REGION=ca-central-1
INGESTION_MODE=sqs
SQS_INGESTION_QUEUE_URL=https://sqs.ca-central-1.amazonaws.com/297784246437/know-your-lease-ingestion-prod
INGESTION_PROCESSING_TIMEOUT_SECONDS=900
```

Secrets Manager values (execution role: `kyl-worker-execution`):

```dotenv
DATABASE_URL=<runtime-postgresql-url>          # created in Phase 6D: know-your-lease/prod/database-url-app
VOYAGE_API_KEY=<secret>                        # know-your-lease/prod/voyage-api-key (created Phase 6C, shared with API)
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

The migration task receives only this Secrets Manager value (execution role:
`kyl-migration-execution`):

```dotenv
DATABASE_URL=<migration-postgresql-url>        # created in Phase 6D: know-your-lease/prod/database-url-migrate
```

The migration task runs with no application task role at all -- it makes no AWS
API calls beyond what its execution role already grants (image pull, log write,
this one secret).

`alembic upgrade head` imports SQLAlchemy metadata but does not import the FastAPI
application. It therefore does not require S3, SQS, Cognito, frontend, Voyage, or
Gemini configuration. Migrations remain separate from API startup.

### Vercel frontend

These are public build-time configuration, not secrets:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://api.<domain>
NEXT_PUBLIC_COGNITO_DOMAIN=https://know-your-lease-prod.auth.ca-central-1.amazoncognito.com
NEXT_PUBLIC_COGNITO_APP_CLIENT_ID=4sq1r3l1flfv1acrkrqc69aoh9
NEXT_PUBLIC_COGNITO_REDIRECT_URI=https://<vercel-production-domain>/auth/callback
```

The Cognito app client (`know-your-lease-web`) is public and has no client secret
(verified: `create-user-pool-client` returned no `ClientSecret` field). Its callback
and logout URLs are currently `http://localhost:3000/auth/callback` and
`http://localhost:3000/` only, because the Vercel production hostname does not
exist yet. Phase 6E must retrieve the client's full current configuration with
`describe-user-pool-client` and re-send every field via `update-user-pool-client`
with the Vercel URLs *appended* to the existing localhost ones -- that API replaces
the entire client configuration, so sending only the new URLs would silently erase
the localhost ones local development still needs.

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

Phase 6B created the VPC, four subnets, Internet Gateway, route tables, security
groups, S3 Gateway endpoint, private RDS instance and RDS-managed master secret,
private S3 bucket, and SQS/DLQ.

Phase 6C created a non-root deployment identity (`kyl-deployer`, see
[docs/aws-identity.md](aws-identity.md)), a live Cognito user pool and public app
client, a Cognito Hosted UI domain, a private ECR repository (empty), the
`voyage-api-key` and `gemini-api-key` application secrets, three ECS execution
roles, and two ECS application task roles.

Phase 6D pushed a `linux/amd64` image to that repository, created the ECS
cluster, four CloudWatch log groups, bootstrapped `kyl_migrate`/`kyl_app`
PostgreSQL roles and the `database-url-app`/`database-url-migrate` secrets from
a temporary in-VPC task (whose IAM access was deleted immediately after), ran
`alembic upgrade head` to `20260904_0006`, and stood up the worker service, the
ALB + target group, and the API service. The API is reachable at
`http://know-your-lease-prod-822884909.ca-central-1.elb.amazonaws.com` for
infrastructure checks only -- **its HTTP:80 listener was deleted** after
verification passed, so nothing currently serves application traffic there; the
ALB, target group, and API service were kept running per the approved
Phase 6D→6E boundary. See
[docs/aws-resource-inventory.md](aws-resource-inventory.md#phase-6d-resources)
for every identifier and
[docs/aws-resource-inventory.md](aws-resource-inventory.md#verified-phase-6d-state)
for what was verified live.

Phase 6D did **not** create: an ACM certificate, an HTTPS listener, a DNS
resource, or a Vercel deployment -- those are Phase 6E. No Cognito callback URL
was changed; the app client still accepts only `localhost` origins.

## Phase 6B live-account deviation

The selected AWS Free plan rejected seven-day RDS automated-backup retention
before creating an instance. The temporary portfolio instance uses one-day
retention instead. Deletion protection remains enabled, and teardown requires an
explicit final-snapshot decision. No other approved RDS sizing or security setting
is changed by this account constraint.

## Phase 6C live-account deviation

`CreateUserPool` rejects `MfaConfiguration=OPTIONAL` (or `ON`) unless SMS/SNS is
also configured, even when the only enabled MFA method is a software token. The
pool was created with `MfaConfiguration=OFF`, then `set-user-pool-mfa-config` was
called separately with `MfaConfiguration=OPTIONAL` and
`SoftwareTokenMfaConfiguration.Enabled=true`. The result is optional TOTP-only
MFA with no SMS/SNS role and no per-message SMS cost -- functionally what was
requested, reached in two API calls instead of one.

## Phase 6D live-account deviations

The `KnowYourLeaseDeployerPolicy` v2 update needed to trim beyond the originally
planned statement set: AWS customer-managed policies are capped at 6,144 bytes,
and the full addition (ECR push, ECS cluster/task/service, log groups, ELBv2,
service-linked-role creation) exceeded it by ~200 bytes with every action
included. `logs:TagResource` and the log-stream-level ARN suffix were dropped
(log groups are created without inline tags as a result; retention and
functionality are unaffected) and new statement `Sid`s were shortened; all 15
pre-existing statements, including all 5 Deny guardrails, were verified
byte-identical before publishing.

Two real bugs surfaced only once the bootstrap task actually ran inside the
VPC, where they could not have been caught by static review:

1. **The RDS-managed master secret contains only `username`/`password`**, not
   connection details. The initial code assumed an RDS-secret shape that
   includes `host`/`port`/`dbname` (true for some AWS-managed secret types, not
   this one) and failed with `KeyError: 'host'`. Fixed by passing the endpoint,
   port, and database name as plain (non-secret) task environment variables
   instead.
2. **PostgreSQL's `CREATE ROLE`/`ALTER ROLE ... PASSWORD` clause rejects a
   query bind parameter** (`syntax error at or near "$1"`) -- the password must
   be a literal in role DDL, unlike ordinary `SELECT`/DML statements. Fixed
   using `psycopg.sql.Literal`, which quotes and escapes the value safely into
   the statement text without the injection risk a raw f-string would carry.

Both fixes required a new image build. Because ECR is `IMMUTABLE` and the
already-pushed tag had already been used in one failed task run, and this
session was instructed not to commit, the corrected builds were pushed as
`<git-sha>-fix1` and `<git-sha>-fix2` rather than reusing or re-deriving the
original SHA tag. `<git-sha>-fix2` is the digest every task definition in this
phase references. **This deviates from pure "one Git SHA, one tag" tagging**;
the honest state is that the image running in AWS contains the
`backend/app/bootstrap/` code as of this session's uncommitted working tree,
not literally the tree at `<git-sha>`. A future commit that includes this code
should re-tag/re-push under the resulting real SHA so the two stay
truthfully linked.
