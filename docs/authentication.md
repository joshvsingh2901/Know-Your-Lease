# Authentication and Document Ownership

Phase 4 turns the single-user/local document model into a real multi-user security
model: every document belongs to exactly one user, and every document-scoped
operation enforces that ownership. This document describes what is implemented in
application code today. **It does not describe provisioned infrastructure**: this
repository does not create or run a live Cognito user pool. `AUTH_MODE=cognito`
requires one to already exist; nothing here stands one up.

## Cognito authentication flow

The frontend uses Cognito's Hosted UI with the standard OAuth2 Authorization Code
flow plus PKCE, implemented directly in `frontend/lib/auth.ts` against Cognito's
plain `/oauth2/authorize`, `/oauth2/token`, and `/logout` endpoints (WebCrypto for the
PKCE challenge) rather than through an auth SDK -- there is exactly one redirect flow
to drive, so a full SDK was unnecessary. The client is a **public client with no
client secret**; a client secret must never ship to a browser.

```text
Browser -> Cognito Hosted UI (sign-in / sign-up)
        <- authorization code
        -> POST /oauth2/token (PKCE verifier)
        <- access token + ID token + refresh token
        -> FastAPI:  Authorization: Bearer <ACCESS token>
```

The **access token**, not the ID token, is sent to the API and is the only token the
backend accepts. This matters concretely: Cognito access tokens carry `token_use:
"access"` and a `client_id` claim, but **no `aud` claim** -- passing `audience=...` to
a JWT library fails every request. The backend checks `client_id` instead, and
explicitly rejects any token whose `token_use` is not `"access"` so an ID token
cannot be substituted for one.

Refresh tokens live entirely in the frontend (`frontend/lib/auth.ts`); the backend is
fully stateless and never sees, stores, or refreshes one. `getAccessToken()` refreshes
silently ~30 seconds before expiry and clears the local session if the refresh fails.

## JWT verification (`backend/app/core/auth.py`)

A request in `AUTH_MODE=cognito` is accepted only if all of the following hold:

- the signature verifies against a Cognito JWKS signing key (RS256 only -- the
  algorithm list is fixed, so an attacker cannot force HS256/"none");
- `iss` matches the configured pool's issuer URL;
- `token_use == "access"`;
- `client_id` matches `COGNITO_APP_CLIENT_ID`;
- `exp`/`nbf` are valid, with up to 60 seconds of clock-skew leeway.

**JWKS caching.** Signing keys are cached in-process by `kid` with a one-hour TTL.
An unknown `kid` forces exactly one refresh -- but that forced refresh is separately
rate-limited (a five-minute cooldown, independent of the normal TTL), so a token
carrying a random/unknown `kid` cannot be used to force repeated outbound requests to
Cognito through the API. If a refresh fails but a previous key set is already cached,
the stale keys are kept and a warning is logged rather than failing every request
outright; if there is no cached key set at all, the request fails as a **503**
(`AuthServiceUnavailableError`), not a 401 -- this is a provider-availability fault,
not a bad credential, and conflating the two would make the frontend treat a
Cognito outage as "your session is invalid" and sign the user out.

**Local user resolution.** A verified subject (`sub`) is looked up in `users` by
`cognito_sub`, or created just-in-time on first sight (`email` from the token's
`email` claim if present, otherwise `NULL`). Two simultaneous first requests from a
brand-new subject can race on that insert; the unique constraint on `cognito_sub` is
the actual guard, and the loser of the race re-reads the row the winner just
committed rather than erroring.

**Error handling.** Every failure mode (missing token, malformed token, expired
token, wrong issuer, wrong client, wrong `token_use`, unknown/invalid signing key)
returns the same generic `401 {"detail": "Not authenticated."}` with a
`WWW-Authenticate: Bearer` header. The response never echoes the token, the Cognito
subject, the issuer, the client ID, or a signature/JWKS parse reason, and none of
those appear in logs either.

## Document ownership (`backend/app/api/document_access.py`)

Every document-scoped route depends on `get_accessible_document` or
`list_accessible_documents` rather than querying `Document` directly, so the
ownership rule exists in exactly one place:

```python
select(Document).where(
    Document.id == document_id,
    Document.owner_id == current_user.id,
)
```

**404, never 403, for an unowned or nonexistent document.** A 403 would confirm the
document *exists*, turning the endpoint into an existence oracle for document UUIDs.
Returning 404 for both "doesn't exist" and "isn't yours" costs nothing here -- the
same query and the same error message produce both cases through one code path --
and it removes the oracle entirely.

**A null `owner_id` is accessible to no one**, not to everyone. `documents.owner_id`
is a nullable foreign key so that pre-authentication rows can exist in the schema
without violating a constraint, but the seam's equality check (`owner_id ==
current_user.id`) can never match `NULL`. A legacy document therefore stays
invisible to every authenticated user until an explicit backfill assigns it (see
Migration below) -- it is never silently treated as public.

**Protected routes:** list (`GET /documents`), upload (`POST /documents`, sets
`owner_id` from the authenticated user -- a request body cannot set or override it),
metadata/status (`GET /documents/{id}`), PDF (`GET /documents/{id}/pdf`), questions
(`POST /documents/{id}/questions`), and both development-only debug routes
(`GET /documents/{id}/chunks`, `POST /documents/{id}/retrieve}`) -- these carry both
the ownership check and the existing `debug_endpoints_allowed` gate, since either one
alone is insufficient. `GET /health` is deliberately exempt: it has no document
context, and the Docker `HEALTHCHECK` plus Railway's activation gate call it without
a token.

## Worker / SQS trust boundary

The SQS message contract, the worker, and Phase 3B's reliability semantics are
**unchanged by this phase**. The message still contains only
`{version, document_id, ingestion_version}` -- no owner ID, no JWT, no email. The
worker is trusted backend infrastructure with no request and no user context, so it
makes no authorization decision; it simply processes the document the database says
exists, and ownership is enforced entirely on the read/write side in
`document_access.py`. Putting an owner field on the queue message would create a
second, potentially stale or forged, source of ownership truth for no benefit --
chunks and cache rows are keyed by `document_id` and inherit ownership through the
document itself, so there is no code path in ingestion that could move data between
owners even if it wanted to.

## Answer cache

`grounded_answer_cache`'s key (`document_id` + normalized question + generation
version) is unchanged and does not carry an `owner_id`. Document IDs are globally
unique, and every read path reaches the cache only after the access seam has already
confirmed the caller owns that document -- a cache hit is structurally unreachable by
anyone else. `AnswerCacheService.get` additionally revalidates that every cited chunk
still belongs to that `document_id`, so a hit cannot reference another document's
chunks even indirectly. Adding `owner_id` to the cache row would duplicate ownership
that is already enforced upstream, with no additional guarantee.

## localStorage

The active-document ID in `localStorage` (`frontend/lib/active-document.ts`) is a UI
convenience only, never an authorization input -- the backend re-checks ownership on
every request regardless of what the client claims to have open. On restore:

- **404** (deleted, or belongs to another user): the stored ID is cleared. A stale ID
  pointing at someone else's document is denied like any nonexistent one, and the
  frontend forgets it.
- **401** (expired/invalid session): the stored ID is preserved, since the document
  itself may still be valid once the user re-authenticates. A blanket "clear on any
  4xx" rule would otherwise make a merely-expired token silently drop the user's open
  lease.
- **Sign-out**: the stored ID is cleared explicitly, so the next person on a shared
  browser starts clean.

## Cognito vs. FastAPI ownership vs. IAM

Three distinct layers, easy to conflate:

- **Cognito** answers "who is this person?" -- user authentication only.
- **FastAPI's ownership seam** answers "can this person see this document?" --
  application authorization, enforced entirely in `document_access.py`.
- **IAM** answers "can this backend process talk to S3/SQS?" -- infrastructure
  access for the API and worker tasks, unrelated to any end user's identity.

A Cognito access token never grants AWS permissions, and an IAM role never implies a
user is allowed to see a particular document.

## Local development (`AUTH_MODE=disabled`)

The default for local development and the entire test suite. Token verification is
skipped entirely, and every request resolves to one fixed local-development user
(`cognito_sub = "local-development-user"`, a fixed UUID). This is not a bypass of the
ownership seam -- the seam still runs, and a document owned by a different user (as
constructed in tests) is still correctly denied; the only thing stubbed out is
Cognito token verification itself. The frontend mirrors this: with no
`NEXT_PUBLIC_COGNITO_*` values set, `AuthGate` renders its children directly with no
sign-in wall, and `lib/api.ts` attaches no `Authorization` header.

## Production requirements

`ENVIRONMENT=production` startup validation (`validate_runtime_settings`) fails
closed if `AUTH_MODE` is unset or is anything other than `cognito`, and
`AUTH_MODE=cognito` itself requires `COGNITO_REGION`, `COGNITO_USER_POOL_ID`, and
`COGNITO_APP_CLIENT_ID` to be set (`COGNITO_ISSUER` is optional and is derived from
region + pool ID when omitted). None of this provisions a Cognito pool; it only
refuses to run a production deployment with authentication silently disabled or
half-configured.

## Migration and backfill

Migration `20260904_0006` is purely additive: a new `users` table and a new nullable
`documents.owner_id` foreign key. It performs no backfill and deletes nothing --
existing documents, chunks, and cached answers are preserved exactly as they were,
and (per the null-owner rule above) become inaccessible to every user until
explicitly assigned. `backend/scripts/backfill_document_owners.py` is the explicit,
manually-invoked assignment step for local development data: it creates the fixed
local-development user if needed and assigns every currently-ownerless document to
it. It refuses to run when `ENVIRONMENT=production`, specifically so a production
database can never have its documents silently reassigned to an arbitrary user. A
later migration (not yet applied) can make `owner_id` `NOT NULL` once a given
database's legacy rows have all been explicitly assigned.

## Current limitations

- No live Cognito user pool is provisioned or run by this repository.
- No re-ingestion endpoint or other producer advances a document past ingestion
  version 1; nothing in the current application requests a higher `ingestion_version`
  for an existing document.
- Access tokens are stored in the browser's `localStorage`, which is readable by any
  successful XSS; an httpOnly-cookie backend-for-frontend would remove that exposure
  but is a materially larger architecture change than this phase's scope.
- There is no document sharing, team/organization model, or admin/role system --
  ownership is strictly one document to exactly one user.
- The `getAccessToken()` + `httpHeaders` path used by the PDF viewer
  (`frontend/components/pdf-viewer-client.tsx`) has only been exercised locally with
  `AUTH_MODE=disabled` (no token attached); its behavior against a real Cognito
  access token has not been verified in a live browser against a real pool.
