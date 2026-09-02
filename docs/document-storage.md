# Document Storage

Phase 2 removes the API and ingestion pipeline's dependence on filesystem paths. PostgreSQL continues to store document metadata and the opaque `uploads/<document-uuid>.pdf` storage key; PDF bytes live in the selected storage backend.

## Storage boundary

`DocumentStorage` defines three operations:

- `save(document_id, source) -> storage_key`
- `read(storage_key) -> bytes`
- `delete(storage_key)` for upload rollback cleanup

`LocalDocumentStorage` and `S3DocumentStorage` implement the same contract. Upload, ingestion, and `GET /documents/{id}/pdf` use only that contract. Original filenames remain display metadata and never become paths or object keys. API responses expose neither storage keys nor backend locations.

The existing key format is retained, so no database migration is needed and existing local PDFs remain usable whenever the local backend points at their current `PDF_STORAGE_DIR`. Switching a database to S3 does not copy existing local files; migration of private data must be a separate, deliberate operation.

## Backend selection

Local development and tests use the default:

```dotenv
DOCUMENT_STORAGE_BACKEND=local
PDF_STORAGE_DIR=./storage
```

Local writes remain atomic through a temporary `.part` file and rename. Keys must match the UUID-owned `uploads/<uuid>.pdf` format, and resolved paths cannot leave the configured uploads root.

Production must set `DOCUMENT_STORAGE_BACKEND` explicitly, preventing an AWS task from silently falling back to its ephemeral filesystem. The value may still be `local` for the existing single-instance Railway volume deployment, but AWS production should select `s3`.

S3 mode requires:

```dotenv
DOCUMENT_STORAGE_BACKEND=s3
S3_BUCKET_NAME=know-your-lease-documents
AWS_REGION=ca-central-1
```

S3 uploads use `PutObject` with `Content-Type: application/pdf` and SSE-S3 (`AES256`). No ACL is sent, so the object retains the bucket's private default and the application does not need `s3:PutObjectAcl`. Enable S3 Block Public Access on the bucket. Reads use the stored key directly; no bucket listing, public URL, or presigned URL is used. Missing objects become a safe application not-found error, while AWS/network failures become fixed storage errors without bucket, key, credential, or provider details.

The current 20 MB default upload limit bounds the in-memory byte read used by ingestion and the backend PDF response. Raising `MAX_UPLOAD_SIZE_MB` substantially should be paired with a future streaming design.

## Credentials and future ECS tasks

There are deliberately no application settings for static access keys. Boto3 uses its standard credential provider chain. Local developers can use an AWS CLI profile, AWS SSO/profile configuration, environment credentials, or fully stubbed tests. Do not put credentials in `backend/.env.example`, source code, image layers, or committed files.

The intended AWS production model is:

```text
ECS API/ingestion task -> IAM task role credentials -> private S3 bucket
```

ECS supplies short-lived task-role credentials through the container credential provider. The execution role used to pull images or write platform logs is separate and should not receive document access.

## Least-privilege IAM example

The current API needs direct object access only under `uploads/`. `DeleteObject` is required for best-effort cleanup when an upload reaches S3 but its database transaction fails. `ListBucket`, object ACL actions, and `s3:*` are not required.

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "KnowYourLeaseDocumentObjects",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::<bucket-name>/uploads/*"
    }
  ]
}
```

Attach this policy to the future ECS **task role**, replacing `<bucket-name>` with the dedicated private bucket. Bucket creation, public-access blocking, lifecycle/retention rules, backups, KMS policy, and ECS provisioning remain future infrastructure work; no Terraform or AWS deployment is included in Phase 2.

## Application flow

Upload validation is unchanged. After validation, the API saves the PDF through the configured backend and then inserts the document row. If the database transaction fails, object deletion is attempted without replacing the safe database error if cleanup also fails. That rare double failure can leave an orphan object for operational reconciliation; no distributed transaction is introduced.

Ingestion resolves the document row's storage key, calls `DocumentStorage.read`, and passes the bytes to the existing PyMuPDF extraction path. Chunking, Voyage embeddings, status transitions, retrieval, Gemini generation, citation verification, and answer caching are unchanged. Ingestion remains an in-process FastAPI background task until the separately scoped worker phase.
