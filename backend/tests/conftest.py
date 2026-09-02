import uuid
from collections.abc import Iterator
from pathlib import Path
from textwrap import wrap

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_db
from app.core.database import Base
from app.main import app
from app.services.document_ingestion import get_ingestion_service
from app.services.storage import (
    DocumentStorage,
    LocalDocumentStorage,
    get_document_storage,
)


class PassiveIngestionService:
    def __init__(self, storage: DocumentStorage) -> None:
        self.storage = storage
        self.requested_documents: list[uuid.UUID] = []

    def process_document(self, document_id: uuid.UUID) -> bool:
        self.requested_documents.append(document_id)
        return True


@pytest.fixture()
def session_factory():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    yield factory
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture()
def db_session(session_factory) -> Iterator[Session]:
    with session_factory() as session:
        yield session


@pytest.fixture()
def client(db_session: Session, tmp_path: Path) -> Iterator[TestClient]:
    def override_get_db():
        yield db_session

    ingestion = PassiveIngestionService(LocalDocumentStorage(tmp_path / "storage"))
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_ingestion_service] = lambda: ingestion
    app.dependency_overrides[get_document_storage] = lambda: ingestion.storage
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture()
def make_pdf():
    def create(path: Path, pages: list[str | None]) -> Path:
        pdf = pymupdf.open()
        for text in pages:
            page = pdf.new_page()
            if text:
                y_position = 60
                for paragraph in text.splitlines():
                    lines = wrap(paragraph, width=95) if paragraph else [""]
                    for line in lines:
                        if y_position >= 790:
                            break
                        if line:
                            page.insert_text((50, y_position), line, fontsize=8)
                        y_position += 10
                    if y_position >= 790:
                        break
        pdf.save(path)
        pdf.close()
        return path

    return create
