"""Run one real Voyage-backed document ingestion against the configured database."""

import argparse
import sys
import uuid
from pathlib import Path

from sqlalchemy import func, select

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.document_ingestion import DocumentIngestionService
from app.services.storage import DocumentStorage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Index one local PDF with Voyage and report its persisted chunks."
    )
    parser.add_argument("pdf", type=Path, help="Path to a small digitally generated lease PDF")
    return parser.parse_args()


def validate_pdf(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if not resolved.is_file() or resolved.suffix.lower() != ".pdf":
        raise SystemExit("Provide an existing PDF file.")
    with resolved.open("rb") as source:
        if source.read(5) != b"%PDF-":
            raise SystemExit("The selected file does not have a valid PDF signature.")
    return resolved


def main() -> int:
    args = parse_args()
    if not settings.voyage_api_key:
        raise SystemExit("VOYAGE_API_KEY is missing from backend/.env or the environment.")

    path = validate_pdf(args.pdf)
    document_id = uuid.uuid4()
    storage = DocumentStorage()
    with path.open("rb") as source:
        storage_key = storage.save(document_id, source)

    try:
        with SessionLocal() as db:
            db.add(
                Document(
                    id=document_id,
                    original_filename=path.name,
                    storage_key=storage_key,
                    status=DocumentStatus.UPLOADED,
                )
            )
            db.commit()
    except Exception:
        storage.delete(storage_key)
        raise

    outcome = DocumentIngestionService(storage=storage).process_document(
        document_id,
        1,
        durable_retries=False,
    )
    with SessionLocal() as db:
        document = db.get(Document, document_id)
        chunk_count = db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        )
        page_numbers = db.scalars(
            select(DocumentChunk.page_number)
            .where(DocumentChunk.document_id == document_id)
            .distinct()
            .order_by(DocumentChunk.page_number)
        ).all()

    if document is None:
        raise SystemExit("The integration-test document record disappeared unexpectedly.")
    print(f"document_id={document.id}")
    print(f"status={document.status.value}")
    print(f"chunks={chunk_count or 0}")
    print(f"pages={','.join(str(page) for page in page_numbers)}")
    if document.error_message:
        print(f"error={document.error_message}")
    return 0 if outcome.acknowledge and document.status == DocumentStatus.READY else 1


if __name__ == "__main__":
    raise SystemExit(main())
