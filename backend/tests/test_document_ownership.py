import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.auth_dependencies import LOCAL_DEV_USER_ID
from app.models.answer_cache import GroundedAnswerCache
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.models.user import User


def _other_user(db: Session, *, cognito_sub: str = "other-user-sub") -> User:
    user = User(cognito_sub=cognito_sub)
    db.add(user)
    db.commit()
    return user


def _document_for(
    db: Session,
    owner_id: uuid.UUID | None,
    *,
    status: DocumentStatus = DocumentStatus.READY,
    filename: str = "lease.pdf",
) -> Document:
    document_id = uuid.uuid4()
    document = Document(
        id=document_id,
        owner_id=owner_id,
        original_filename=filename,
        storage_key=f"uploads/{document_id}.pdf",
        status=status,
    )
    db.add(document)
    db.commit()
    return document


def test_user_lists_only_their_own_documents(client: TestClient, db_session: Session) -> None:
    mine = _document_for(db_session, LOCAL_DEV_USER_ID, filename="mine.pdf")
    other_user = _other_user(db_session)
    _document_for(db_session, other_user.id, filename="not-mine.pdf")

    response = client.get("/documents")

    assert response.status_code == 200
    items = response.json()["items"]
    assert [item["id"] for item in items] == [str(mine.id)]


def test_user_a_cannot_read_user_b_metadata(client: TestClient, db_session: Session) -> None:
    other_user = _other_user(db_session)
    other_document = _document_for(db_session, other_user.id)

    response = client.get(f"/documents/{other_document.id}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


def test_user_a_cannot_fetch_user_b_pdf(
    client: TestClient, db_session: Session, tmp_path: Path
) -> None:
    other_user = _other_user(db_session)
    other_document = _document_for(db_session, other_user.id)
    storage_dir = tmp_path / "storage" / "uploads"
    storage_dir.mkdir(parents=True, exist_ok=True)
    (storage_dir / f"{other_document.id}.pdf").write_bytes(b"%PDF-1.4\nsecret clause\n%%EOF")

    response = client.get(f"/documents/{other_document.id}/pdf")

    assert response.status_code == 404
    assert b"secret clause" not in response.content


def test_user_a_cannot_ask_questions_against_user_b_document(
    client: TestClient, db_session: Session
) -> None:
    other_user = _other_user(db_session)
    other_document = _document_for(db_session, other_user.id)

    response = client.post(
        f"/documents/{other_document.id}/questions",
        json={"question": "Can I sublet?"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


def test_user_a_cannot_access_user_b_debug_chunks(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.routes.documents.settings.debug_endpoints_enabled", True)
    other_user = _other_user(db_session)
    other_document = _document_for(db_session, other_user.id)
    db_session.add(
        DocumentChunk(
            document_id=other_document.id,
            chunk_index=0,
            text="This lease's secret clause",
            page_number=1,
            token_count=3,
            embedding=[0.1] * 1024,
        )
    )
    db_session.commit()

    response = client.get(f"/documents/{other_document.id}/chunks")

    assert response.status_code == 404
    assert "secret clause" not in response.text


def test_user_a_cannot_access_user_b_debug_retrieval(
    client: TestClient, db_session: Session, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.routes.documents.settings.debug_endpoints_enabled", True)
    other_user = _other_user(db_session)
    other_document = _document_for(db_session, other_user.id)

    response = client.post(
        f"/documents/{other_document.id}/retrieve",
        json={"question": "Can I sublet?"},
    )

    assert response.status_code == 404


def test_user_a_cannot_use_user_b_cached_answer(
    client: TestClient, db_session: Session
) -> None:
    other_user = _other_user(db_session)
    other_document = _document_for(db_session, other_user.id)
    chunk = DocumentChunk(
        document_id=other_document.id,
        chunk_index=0,
        text="Subletting requires written consent.",
        page_number=1,
        token_count=4,
        embedding=[0.1] * 1024,
    )
    db_session.add(chunk)
    db_session.flush()
    db_session.add(
        GroundedAnswerCache(
            document_id=other_document.id,
            normalized_question="can i sublet?",
            generation_version="v1",
            answer="Yes, with the landlord's written consent.",
            citations=[{"chunk_id": str(chunk.id)}],
        )
    )
    db_session.commit()

    response = client.post(
        f"/documents/{other_document.id}/questions",
        json={"question": "Can I sublet?"},
    )

    assert response.status_code == 404
    assert "written consent" not in response.text


@pytest.mark.parametrize(
    ("method", "suffix", "json_body"),
    [
        ("GET", "", None),
        ("GET", "/pdf", None),
        ("GET", "/chunks", None),
        ("POST", "/retrieve", {"question": "Can I have pets?"}),
        ("POST", "/questions", {"question": "Can I have pets?"}),
    ],
)
def test_possession_of_another_users_document_uuid_grants_no_access(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
    method: str,
    suffix: str,
    json_body: dict[str, str] | None,
) -> None:
    monkeypatch.setattr("app.api.routes.documents.settings.debug_endpoints_enabled", True)
    other_user = _other_user(db_session)
    other_document = _document_for(db_session, other_user.id)

    response = client.request(
        method, f"/documents/{other_document.id}{suffix}", json=json_body
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


def test_upload_owner_comes_from_the_authenticated_user_not_the_request(
    client: TestClient, db_session: Session
) -> None:
    other_user = _other_user(db_session)

    response = client.post(
        "/documents",
        files={"file": ("lease.pdf", b"%PDF-1.4\n%%EOF", "application/pdf")},
        data={"owner_id": str(other_user.id)},
    )

    assert response.status_code == 201
    document = db_session.get(Document, uuid.UUID(response.json()["id"]))
    assert document is not None
    assert document.owner_id == LOCAL_DEV_USER_ID
    assert document.owner_id != other_user.id


def test_ownerless_legacy_document_is_invisible_to_every_authenticated_user(
    client: TestClient, db_session: Session
) -> None:
    legacy = _document_for(db_session, None, filename="legacy.pdf")

    list_response = client.get("/documents")
    detail_response = client.get(f"/documents/{legacy.id}")

    assert legacy.id not in {
        uuid.UUID(item["id"]) for item in list_response.json()["items"]
    }
    assert detail_response.status_code == 404


def test_stale_localstorage_document_id_for_another_user_is_denied(
    client: TestClient, db_session: Session
) -> None:
    other_user = _other_user(db_session)
    other_document = _document_for(db_session, other_user.id)

    response = client.get(f"/documents/{other_document.id}")

    assert response.status_code == 404
