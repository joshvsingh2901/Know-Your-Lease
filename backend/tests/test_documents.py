import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.main import app
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.document_ingestion import get_ingestion_service


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


def test_document_library_lists_only_safe_document_metadata(
    client: TestClient,
    db_session: Session,
) -> None:
    first = Document(original_filename="first.pdf", storage_key="uploads/private.pdf")
    second = Document(original_filename="second.pdf", status=DocumentStatus.READY)
    db_session.add_all([first, second])
    db_session.commit()

    response = client.get("/documents")

    assert response.status_code == 200
    items = response.json()["items"]
    assert {item["filename"] for item in items} == {"first.pdf", "second.pdf"}
    assert all("storage_key" not in item for item in items)


def test_listing_ready_document_for_reopen_does_not_schedule_ingestion(
    client: TestClient,
    db_session: Session,
) -> None:
    document = Document(original_filename="ready.pdf", status=DocumentStatus.READY)
    db_session.add(document)
    db_session.commit()
    ingestion = app.dependency_overrides[get_ingestion_service]()

    response = client.get("/documents")

    assert response.status_code == 200
    assert response.json()["items"][0]["id"] == str(document.id)
    assert ingestion.requested_documents == []


def test_debug_chunks_endpoint_is_hidden_when_disabled(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = Document(original_filename="lease.pdf", status=DocumentStatus.READY)
    db_session.add(document)
    db_session.commit()
    monkeypatch.setattr("app.api.routes.documents.settings.debug_endpoints_enabled", False)

    response = client.get(f"/documents/{document.id}/chunks")

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found."}


def test_missing_document_returns_not_found(client: TestClient) -> None:
    response = client.get(f"/documents/{uuid.uuid4()}")

    assert response.status_code == 404


def test_document_pdf_streams_from_document_storage(
    client: TestClient,
    db_session: Session,
    tmp_path: Path,
) -> None:
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        original_filename="lease.pdf",
        storage_key=f"uploads/{document_id}.pdf",
        status=DocumentStatus.READY,
    )
    db_session.add(document)
    db_session.commit()
    expected_pdf = b"%PDF-1.4\nPDF body\n%%EOF"
    stored_pdf = tmp_path / "storage" / "uploads" / f"{document_id}.pdf"
    stored_pdf.parent.mkdir(parents=True)
    stored_pdf.write_bytes(expected_pdf)

    response = client.get(f"/documents/{document_id}/pdf")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/pdf")
    assert response.headers["cache-control"] == "no-store"
    assert response.content == expected_pdf


def test_document_pdf_missing_storage_file_is_safe_and_does_not_leak_path(
    client: TestClient,
    db_session: Session,
) -> None:
    document_id = uuid.uuid4()
    db_session.add(
        Document(
            id=document_id,
            original_filename="lease.pdf",
            storage_key=f"uploads/{document_id}.pdf",
            status=DocumentStatus.READY,
        )
    )
    db_session.commit()

    response = client.get(f"/documents/{document_id}/pdf")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document PDF is unavailable."}
    assert "uploads" not in response.text


def test_nonexistent_document_pdf_returns_not_found(client: TestClient) -> None:
    response = client.get(f"/documents/{uuid.uuid4()}/pdf")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}
