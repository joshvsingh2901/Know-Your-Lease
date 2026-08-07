from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.document import Document, DocumentStatus


def test_valid_pdf_upload_creates_document(
    client: TestClient, db_session: Session
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

    document = db_session.scalar(select(Document))
    assert document is not None
    assert str(document.id) == body["id"]
    assert document.original_filename == "my-lease.pdf"
    assert document.status == DocumentStatus.UPLOADED


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
