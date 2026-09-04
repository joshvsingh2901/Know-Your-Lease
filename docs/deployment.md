# Deployment Overview

The repository is prepared for an AWS production deployment but is not currently
serving the application. Phase 6A introduced workload-specific configuration, and
Phase 6B provisioned the temporary network/data plane. Compute, public ingress,
identity, application IAM/secrets, and frontend deployment remain pending.

## Current production target

The approved target is:

```text
Vercel Next.js
  -> Cognito managed login / PKCE
  -> HTTPS Application Load Balancer
  -> ECS/Fargate FastAPI API
       -> private S3 documents
       -> SQS ingestion queue + DLQ
       -> RDS PostgreSQL + pgvector
       -> Voyage and Gemini

SQS -> ECS/Fargate ingestion worker -> S3, RDS, Voyage
```

The region is `ca-central-1`. The initial API and worker services each use 0.25
vCPU, 1 GiB, and desired count one. Alembic runs as a one-off 0.25-vCPU/1-GiB
Fargate task. ECS tasks use public subnets for controlled outbound access; RDS
uses isolated subnets, and no NAT Gateway is planned initially.

See [AWS deployment preparation](aws-deployment.md) for the exact API, worker,
migration, and frontend configuration maps, workload commands, secret split, and
Phase 6 boundary.

## Shared image contract

One image built from `backend/Dockerfile` supports:

- API: the existing default Uvicorn command
- Worker: `python -m app.workers.ingestion`
- Worker health check: `python -m app.workers.ingestion --check`
- Migration: `alembic upgrade head`

Migrations remain separate from application startup. Production API validation
requires the complete AWS/Cognito/provider configuration. Worker validation
requires only ingestion configuration. Migration validation requires only an
explicit database URL.

## Frontend contract

Vercel receives `NEXT_PUBLIC_API_BASE_URL` and the public Cognito domain,
app-client ID, and redirect URI. The API receives the exact Vercel production
origin through `FRONTEND_ORIGIN`. Preview domains are not production CORS origins
or Cognito callbacks.

## Legacy Railway configuration

`railway.toml` is retained as repository history and a possible development/demo
reference. Its former local-volume, inline-ingestion production configuration no
longer satisfies the AWS production API validator, which now deliberately requires
S3 and SQS. It must not be treated as the current production runbook.

## Current status

The VPC, subnets, routing, scoped security groups, S3 Gateway endpoint, private RDS
PostgreSQL instance, private S3 bucket, and encrypted SQS/DLQ now exist in
`ca-central-1`. Exact identifiers, verification, costs, and teardown commands are
in [the resource inventory](aws-resource-inventory.md). No ALB, ECS cluster or
service, ECR repository, Cognito pool, application IAM role/secret, DNS record, or
Vercel deployment has been created.
