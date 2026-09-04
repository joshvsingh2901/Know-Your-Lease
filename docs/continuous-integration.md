# Continuous Integration

Phase 5 adds verification only. It does not deploy the application, publish an
image, provision AWS resources, or configure GitHub branch protection.

## Workflow and triggers

`.github/workflows/ci.yml` runs for pull requests targeting `main`, pushes to
`main`, and manual `workflow_dispatch` runs. Its independent jobs run in parallel
and expose four stable check names:

| Required check | Validation |
| --- | --- |
| `Backend` | Python 3.13.5 dependency installation, `pip check`, Ruff, and the backend pytest suite |
| `Frontend` | Node.js 24 `npm ci`, ESLint, TypeScript, native Node tests, and the Next.js production build |
| `Database/Migrations` | Single-head migration graph validation and `alembic upgrade head` against a clean PostgreSQL 18 database with pgvector |
| `Docker Build` | A cached Buildx build of the production backend/worker image for `linux/amd64`, without a registry push |

No core check uses `continue-on-error`. A dependency, lint, type, test,
migration, frontend build, or Docker build failure therefore fails its job.

## Zero-production-secret design

CI requires no repository or environment secrets. Backend tests use their
existing in-memory database fixtures, generated local JWT keys and fake JWKS
client, boto3 stubs with test-only credentials, and mocked Voyage/Gemini
boundaries. The frontend leaves Cognito unconfigured and uses only the local
reserved `https://api.example.invalid` origin while exercising its production
build validation. The migration job uses an ephemeral
PostgreSQL service with deterministic CI-only credentials.

The workflow never reads production database credentials, provider keys,
Cognito values, or AWS credentials. It also never contacts Railway, AWS,
Voyage, Gemini, or a live Cognito pool.

## Migration validation

The migration job loads the complete Alembic graph and fails unless it has
exactly one head. It then prints the graph, upgrades a clean pgvector-capable
database to `head`, and verifies that the database contains every head.
Migration `20260806_0001` creates the `vector` extension, so the clean upgrade
also proves that the selected PostgreSQL service supports pgvector.

Downgrade/upgrade round-trips are intentionally excluded from routine CI. Before
a release that changes migrations, the manual release check is to run the full
round-trip against a new disposable database that contains no user data:

```bash
cd backend
alembic upgrade head
alembic downgrade base
alembic upgrade head
alembic current --check-heads
```

Never run that destructive downgrade check against a shared, staging, or
production database.

## Branch protection

After the workflow has completed once on GitHub, configure the `main` branch
ruleset manually to require these exact status checks before merging:

- `Backend`
- `Frontend`
- `Database/Migrations`
- `Docker Build`

Do not require a deployment check: this phase includes no continuous delivery.

## Equivalent local checks

```bash
cd backend
source .venv/bin/activate
python -m pip check
ruff check .
pytest

cd ../frontend
npm ci
npm run lint
npm run typecheck
npm test
npm run build

cd ..
docker compose up -d database
cd backend
alembic heads
alembic upgrade head
alembic current --check-heads

cd ..
docker build --platform linux/amd64 --tag know-your-lease-backend:ci backend
git diff --check
```
