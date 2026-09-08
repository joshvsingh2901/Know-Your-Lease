# Deployment Overview

The application is deployed for production validation. The Next.js frontend is
served by Vercel at `https://know-your-lease-tawny.vercel.app`, Cognito provides
Authorization Code + PKCE login, and the API is served over trusted HTTPS at
`https://api.joshveer.ca` through the existing AWS ALB and ECS/Fargate service.

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

The live production values are:

```dotenv
NEXT_PUBLIC_API_BASE_URL=https://api.joshveer.ca
NEXT_PUBLIC_COGNITO_DOMAIN=https://know-your-lease-prod.auth.ca-central-1.amazoncognito.com
NEXT_PUBLIC_COGNITO_APP_CLIENT_ID=4sq1r3l1flfv1acrkrqc69aoh9
NEXT_PUBLIC_COGNITO_REDIRECT_URI=https://know-your-lease-tawny.vercel.app/auth/callback
```

The Vercel project is `know-your-lease` on the Hobby plan, with repository root
`frontend`. Its stable production domain is
`https://know-your-lease-tawny.vercel.app`. The production deployment was made
with the Vercel CLI from application sources at `main` commit `027d145`; Vercel
recorded the checkout as dirty only because its generated `.vercel` ignore entry
was present. Automatic Git deployments are not enabled yet because the Vercel
GitHub App still needs access to the `joshvsingh2901/Know-Your-Lease` repository.

## Legacy Railway configuration

`railway.toml` is retained as repository history and a possible development/demo
reference. Its former local-volume, inline-ingestion production configuration no
longer satisfies the AWS production API validator, which now deliberately requires
S3 and SQS. It must not be treated as the current production runbook.

## Current status

The AWS data plane, ECS API and worker, Cognito pool, ACM certificate, HTTPS ALB
listener, `api.joshveer.ca` DNS record, and Vercel frontend are live. API task
definition revision 3 carries
`FRONTEND_ORIGIN=https://know-your-lease-tawny.vercel.app`; the worker remains on
revision 2. Live checks verified the frontend and API over trusted HTTPS, exact-
origin CORS, rejection of an unrelated origin, a `401` for unauthenticated
`GET /documents`, a complete real-browser Cognito code+PKCE login, and authenticated
upload/rendering of a synthetic PDF over HTTPS.

Authorize the Vercel GitHub App for this repository if automatic Git deployments
are desired. The ALB security group's unused public TCP/80 rule was removed
manually via the AWS Console on 2026-09-08 (`kyl-deployer` still lacks
`ec2:RevokeSecurityGroupIngress` and did not perform the removal); only TCP/443
ingress remains, confirmed by a post-change connection failure on port 80 and
continued healthy HTTPS traffic, ALB target health, and ECS service stability.

## Remaining manual deployment actions

To enable automatic Git deployments, grant the Vercel GitHub App access to
`joshvsingh2901/Know-Your-Lease` in GitHub, then connect it from the repository
root:

```bash
npx --yes vercel@latest git connect https://github.com/joshvsingh2901/Know-Your-Lease.git
```

The unused TCP/80 rule has been removed. It required broad-enough access that
`kyl-deployer` was not granted the narrow `ec2:RevokeSecurityGroupIngress`
statement for this; instead an account administrator removed the rule directly
via the AWS Console on 2026-09-08. Post-change verification with `kyl-deploy`
confirmed the security group now allows only TCP/443, `https://api.joshveer.ca/health`
still returns `200`, the ALB target group remains `healthy`, and both the
`know-your-lease-api` and `know-your-lease-worker` ECS services remain stable
on their existing task definitions.
