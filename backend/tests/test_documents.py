import uuid
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk


def test_valid_pdf_upload_creates_document(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    response = client.post(
        "/documents",
        files={"file": ("my-lease.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["filename"] == "my-lease.pdf"
    assert body["status"] == "uploaded"
    assert body["id"]
    assert body["created_at"]
    assert body["updated_at"]
    assert body["error_message"] is None

    document = db_session.scalar(select(Document))
    assert document is not None
    assert str(document.id) == body["id"]
    assert document.original_filename == "my-lease.pdf"
    assert document.status == DocumentStatus.UPLOADED
    assert document.storage_key == f"uploads/{document.id}.pdf"
    assert (tmp_path / "storage" / document.storage_key).is_file()


def test_non_pdf_upload_is_rejected(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/documents",
        files={"file": ("notes.txt", b"not a pdf", "text/plain")},
    )

    assert response.status_code == 415
    assert db_session.scalar(select(Document)) is None


def test_spoofed_pdf_is_rejected(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/documents",
        files={"file": ("notes.pdf", b"not a pdf", "application/pdf")},
    )

    assert response.status_code == 415
    assert db_session.scalar(select(Document)) is None


def test_original_filename_is_sanitized(client: TestClient, db_session: Session) -> None:
    response = client.post(
        "/documents",
        files={"file": ("../../private/lease.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
    )

    assert response.status_code == 201
    assert response.json()["filename"] == "lease.pdf"
    document = db_session.scalar(select(Document))
    assert document is not None
    assert document.original_filename == "lease.pdf"


def test_get_document_and_paginated_chunks_exclude_embeddings(
    client: TestClient,
    db_session: Session,
) -> None:
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        original_filename="indexed.pdf",
        status=DocumentStatus.READY,
    )
    db_session.add(document)
    db_session.add_all(
        DocumentChunk(
            document_id=document_id,
            chunk_index=index,
            text=f"Lease clause {index}",
            page_number=index + 1,
            paragraph_index=index,
            token_count=3,
            embedding=[float(index)] * 1024,
        )
        for index in range(2)
    )
    db_session.commit()

    status_response = client.get(f"/documents/{document_id}")
    chunks_response = client.get(f"/documents/{document_id}/chunks?limit=1&offset=1")

    assert status_response.status_code == 200
    assert status_response.json()["status"] == "ready"
    assert chunks_response.status_code == 200
    body = chunks_response.json()
    assert body["total"] == 2
    assert body["limit"] == 1
    assert body["offset"] == 1
    assert body["items"][0]["chunk_index"] == 1
    assert body["items"][0]["page_number"] == 2
    assert "embedding" not in body["items"][0]


def test_missing_document_returns_not_found(client: TestClient) -> None:
    response = client.get(f"/documents/{uuid.uuid4()}")

    assert response.status_code == 404
