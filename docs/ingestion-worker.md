# SQS Ingestion Worker

Phase 3A separates production ingestion from the FastAPI process. The API remains responsible for validating and storing a PDF, creating its document row, and publishing a small SQS message. A standalone process reuses the existing ingestion service for extraction, chunking, embeddings, and transactional chunk persistence.

## Modes and flow

Local development defaults to the existing background-task path:

```dotenv
INGESTION_MODE=inline
```

The document moves from `uploaded` to `processing`, then `ready` or `failed`. This mode needs no AWS account and is intended for development and focused testing.

SQS mode requires explicit queue configuration:

```dotenv
INGESTION_MODE=sqs
SQS_INGESTION_QUEUE_URL=https://sqs.ca-central-1.amazonaws.com/<account-id>/<queue-name>
AWS_REGION=ca-central-1
```

The API flow is:

```text
validate PDF -> DocumentStorage.save -> commit Document(status=queued)
             -> SQS SendMessage -> return 201
```

No extraction, chunking, embedding, or vector persistence runs in the request process in SQS mode. If publishing fails, the API records `failed` with a safe error and returns 503. The stored object is retained deliberately; Phase 3A does not add a distributed transaction or automatic orphan cleanup.

The message contract contains identifiers only:

```json
{"version":1,"document_id":"<uuid>"}
```

PDF bytes, extracted lease text, vectors, filenames, credentials, and other private content are never placed in the queue message. Unknown fields, unsupported versions, malformed JSON, and invalid UUIDs fail validation.

## Worker

Run the worker from the backend environment:

```bash
cd backend
source .venv/bin/activate
python -m app.workers.ingestion
```

Or override the command of the same backend image used by the API:

```bash
docker run --rm --env-file backend/.env \
  --health-cmd=none \
  know-your-lease-api:phase3a \
  python -m app.workers.ingestion
```

`python -m app.workers.ingestion --check` validates worker configuration without contacting SQS, PostgreSQL, Voyage, or Gemini. It is suitable for a local/container startup smoke test without an AWS account.

The worker long-polls for one message at a time with `WaitTimeSeconds=20`. It validates the message, verifies the document exists using a fresh SQLAlchemy session, and calls `DocumentIngestionService.process_document`. That existing service marks the document `processing`, reads the PDF through `DocumentStorage`, runs the unchanged PyMuPDF/chunking/Voyage pipeline, and commits chunks plus `ready`. Each service operation creates its own database session; no FastAPI request session is involved.

The SQS receipt is deleted only after the ingestion service reports success. A processing failure, missing document, malformed message, database error, or acknowledgement failure leaves the message undeleted. Queue polling errors use a five-second delay; empty receives naturally wait through SQS long polling.

## IAM split

Scope both policies to the dedicated queue ARN and document-object prefix; do not grant `sqs:*` or `s3:*`.

The API task needs:

- `sqs:SendMessage` on the ingestion queue.
- `s3:PutObject` for upload, `s3:GetObject` for the PDF endpoint, and `s3:DeleteObject` for database-commit rollback, all on `<bucket>/uploads/*` when S3 storage is selected.

The worker task needs:

- `sqs:ReceiveMessage` and `sqs:DeleteMessage` on the ingestion queue.
- `s3:GetObject` on `<bucket>/uploads/*` when S3 storage is selected.

Phase 3A does not call `ChangeMessageVisibility` or `GetQueueAttributes`, so those permissions are not required. Boto3 uses its standard credential chain; future ECS tasks should receive these permissions through separate task roles rather than static access keys.

## Delivery semantics and Phase 3B boundary

SQS delivery is at least once. Phase 3A deliberately does not claim exactly-once processing or complete crash recovery. A successful ingestion followed by a failed delete can be delivered again, and malformed or permanently failing messages remain subject to the queue's configured visibility and redrive behavior.

Phase 3B still needs retry classification/backoff policy, idempotency/versioning, DLQ and poison-message handling, distributed concurrency controls, visibility-timeout renewal where justified, and operational metrics/alarms. Those behaviors are not simulated in Phase 3A application code.
