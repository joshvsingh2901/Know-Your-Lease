# SQS Ingestion Reliability

Phase 3B keeps the Phase 3A API → SQS → worker boundary and makes processing idempotent under SQS at-least-once delivery. The API publishes an identifier and ingestion version; the worker reuses `DocumentIngestionService` for the unchanged extraction, chunking, Voyage embedding, and PostgreSQL/pgvector pipeline.

## Modes and message contract

Local development remains AWS-free with `INGESTION_MODE=inline`. SQS mode requires `SQS_INGESTION_QUEUE_URL` and `AWS_REGION`; boto3 uses its normal credential chain rather than application-managed static keys.

The JSON message contains no document content:

```json
{"version":1,"document_id":"<uuid>","ingestion_version":1}
```

`version` is the message-schema version. `ingestion_version` identifies the requested index generation for that document. Unknown fields, unsupported schema versions, non-positive ingestion versions, malformed JSON, and invalid UUIDs fail validation without mutating a document.

For a safe rolling upgrade, Phase 3A messages that predate the field are interpreted as ingestion version 1. All newly published messages include the field explicitly.

## Idempotent claim and completion

Each document stores its current and completed ingestion versions, total claimed attempts, last safe error code, and last start/failure timestamps. A worker handles a valid message as follows:

- An older version is stale: skip processing and acknowledge it.
- A current version already recorded as `ready`/completed is a duplicate: skip processing and acknowledge it.
- A version newer than the document record is invalid/out of order: do not process or acknowledge it, allowing redrive to the DLQ.
- A fresh `processing` claim is busy: do not process or acknowledge the duplicate.
- A `processing` claim older than `INGESTION_PROCESSING_TIMEOUT_SECONDS` can be reclaimed after a crash.
- A current `queued` or `uploaded` version is atomically changed to `processing`, and its attempt number is incremented.
- A processing attempt that ends in a durably recorded permanent document failure (`status=failed`) is acknowledged: the outcome is already safely persisted, so redelivering it would only repeat wasted work.
- A processing attempt that ends in a transient/retryable failure is not acknowledged, so SQS redelivers it for another attempt.

The atomic conditional update prevents two workers from claiming a fresh version simultaneously. Completion also checks the document version and attempt number under a PostgreSQL row lock. If another attempt reclaimed the job or a newer ingestion version was requested, the older attempt cannot replace chunks or invalidate cache entries. The existing unique `(document_id, chunk_index)` constraint remains a final duplicate defense.

## Transaction and cache boundary

PDF reads, extraction, chunk construction, and provider calls occur without a long-lived database transaction. After all embeddings exist, one short transaction:

1. locks and revalidates the document version and attempt;
2. deletes the previous document chunks;
3. inserts the complete replacement index;
4. invalidates that document's exact-question cache;
5. records the completed version and marks `ready`;
6. commits everything together.

A failed transaction rolls back chunk deletion, insertion, cache deletion, and readiness together. Previously committed chunks/cache may remain while the document is non-ready, but question APIs cannot serve them. Cache invalidation therefore happens exactly once for the successful new version, not when an attempt merely starts. Duplicate and stale deliveries do not touch the cache.

## Retry and status model

Voyage retains its existing bounded retry policy: at most two brief internal retries for 429, 5xx, timeout, or unavailable failures, including existing rate-budget pacing and `Retry-After` handling. After those attempts, the worker uses SQS visibility/redelivery as the outer durable retry layer; it does not re-enqueue messages.

Retryable SQS failures include transient Voyage/provider errors, temporary storage failures, and database failures. The document returns to `queued`, records a safe code such as `provider_rate_limit`, `provider_unavailable`, `storage_unavailable`, or `database_error`, and the message remains undeleted. Inline development has no durable redelivery mechanism, so an exhausted transient attempt becomes `failed` instead of remaining queued forever.

Permanent document failures include corrupt/image-only PDFs, missing/invalid stored objects or metadata, deterministic embedding errors, and provider configuration errors. They mark the document `failed` and, because that failure is durably committed before the worker responds, the message is acknowledged and deleted. The failure is discoverable through the document's own `status`/`error_message`/`last_ingestion_error_code`, not by holding a redundant copy of it in the DLQ. Malformed/poison messages (invalid JSON, unsupported schema version, non-positive ingestion version, unparseable UUID) are different: nothing is recorded for them, so they are never acknowledged and rely entirely on the queue's redrive policy to reach the DLQ after `maxReceiveCount` deliveries.

The resulting status flow is:

```text
uploaded -> queued -> processing -> ready
                         |            ^
                         v            |
                 queued (retryable) --+
                         |
                         +-> failed (terminal)
```

Attempt/error metadata is internal and not exposed in document API responses. Frontend polling continues for `queued` and `processing`, and stops for `ready` or terminal `failed`.

## Crash boundaries

- Before the claim commits: no state changes; the undeleted message can be retried.
- After `processing` but before embeddings complete: the claim becomes reclaimable after the processing timeout.
- During final persistence: PostgreSQL rolls back the entire replacement transaction; the message remains undeleted.
- After final commit but before `DeleteMessage`: redelivery observes the same version already completed and acknowledges it without reading the PDF, embedding, deleting chunks, or invalidating cache again.

This is at-least-once delivery plus idempotent processing, not exactly-once delivery. A worker that exceeds the processing timeout can overlap a reclaiming attempt and cause duplicate provider work, but version/attempt checks prevent the older attempt from committing stale data.

## SQS queue and DLQ settings

Use AWS-native redrive from the main queue to a dedicated DLQ. The application does not send directly to the DLQ and needs no DLQ URL/ARN configuration.

Recommended starting settings:

- Long polling: 20 seconds, matching the worker.
- Visibility timeout: 15 minutes, matching the default 900-second processing timeout; increase both above measured high-percentile ingestion duration plus margin for larger leases.
- Main queue retention: 4 days.
- Redrive `maxReceiveCount`: 5.
- DLQ retention: 14 days, longer than the main queue.
- CloudWatch alarms: visible DLQ messages, oldest main-queue message age, and sustained queue depth.

No visibility heartbeat is implemented. Operations must size the queue visibility timeout and `INGESTION_PROCESSING_TIMEOUT_SECONDS` consistently. Poison/malformed, missing-document, future-version, and busy-duplicate messages remain undeleted and are spaced by SQS visibility before AWS redrives them; there is no application tight loop. Recorded terminal document failures are acknowledged and do not reach the DLQ, since their outcome is already durably captured on the document row.

## IAM split

Scope policies to the dedicated queue ARN and document object prefix. Do not grant `sqs:*`, `s3:*`, or application access to send directly to the DLQ.

The API task needs `sqs:SendMessage` on the main ingestion queue plus its Phase 2 S3 `PutObject`, `GetObject`, and rollback `DeleteObject` permissions on `<bucket>/uploads/*`.

The worker task needs `sqs:ReceiveMessage` and `sqs:DeleteMessage` on the main queue plus `s3:GetObject` on `<bucket>/uploads/*`. It does not call `ChangeMessageVisibility` or `GetQueueAttributes`, so those permissions are not needed.

## Running the worker

```bash
cd backend
source .venv/bin/activate
python -m app.workers.ingestion
```

The same backend image supports the worker command. Disable or replace the image's API HTTP health check for worker containers. `python -m app.workers.ingestion --check` validates configuration without contacting SQS, PostgreSQL, Voyage, or Gemini.

AWS queue/DLQ/IAM provisioning, automated DLQ replay, operator dashboards, visibility heartbeats, and cross-process Voyage rate coordination remain infrastructure/operations work; they are not implemented in application code.

## Current limitation: no re-ingestion producer

`current_ingestion_version` and `completed_ingestion_version` exist to make ingestion idempotent, protect against stale/duplicate delivery, and resolve concurrent workers safely. Every document is created at version 1, and nothing in this phase increments `current_ingestion_version` past that. There is no re-ingestion API endpoint or other producer that requests a later version. Re-ingestion (for example, after a chunking/embedding model change) is deliberately deferred; the version machinery is ready for it, but wiring a producer is out of scope for Phase 3B.
