import uuid
from pathlib import Path

from sqlalchemy import func, select

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.document_ingestion import DocumentIngestionService
from app.services.embeddings import EmbeddingProviderError
from app.services.storage import DocumentStorage


class FakeEmbeddingService:
    def embed_documents(self, texts: list[str], token_counts: list[int]) -> list[list[float]]:
        assert len(texts) == len(token_counts)
        return [[float(index)] * 1024 for index in range(len(texts))]


class FailingEmbeddingService:
    def embed_documents(self, texts: list[str], token_counts: list[int]) -> list[list[float]]:
        raise EmbeddingProviderError("provider unavailable")


def stored_document(session_factory, storage: DocumentStorage, pdf_path: Path) -> uuid.UUID:
    document_id = uuid.uuid4()
    with pdf_path.open("rb") as source:
        storage_key = storage.save(document_id, source)
    with session_factory() as db:
        db.add(
            Document(
                id=document_id,
                original_filename="lease.pdf",
                storage_key=storage_key,
                status=DocumentStatus.UPLOADED,
            )
        )
        db.commit()
    return document_id


def test_valid_pdf_becomes_ready_with_document_scoped_chunks(
    tmp_path: Path,
    make_pdf,
    session_factory,
) -> None:
    lease_text = "\n\n".join(
        f"Clause {index}. The tenant shall pay rent and follow this written obligation."
        for index in range(90)
    )
    pdf_path = make_pdf(tmp_path / "lease.pdf", [lease_text, lease_text])
    storage = DocumentStorage(tmp_path / "storage")
    document_id = stored_document(session_factory, storage, pdf_path)
    service = DocumentIngestionService(
        session_factory=session_factory,
        storage=storage,
        embedding_service=FakeEmbeddingService(),
    )

    assert service.process_document(document_id) is True

    with session_factory() as db:
        document = db.get(Document, document_id)
        chunks = db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index)
        ).all()
        assert document is not None
        assert document.status == DocumentStatus.READY
        assert document.error_message is None
        assert len(chunks) >= 2
        assert all(chunk.document_id == document_id for chunk in chunks)
        assert {chunk.page_number for chunk in chunks} == {1, 2}
        assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))


def test_embedding_failure_marks_failed_and_removes_partial_index(
    tmp_path: Path,
    make_pdf,
    session_factory,
) -> None:
    pdf_path = make_pdf(
        tmp_path / "lease.pdf",
        ["The tenant must pay rent on the first day of every month. " * 20],
    )
    storage = DocumentStorage(tmp_path / "storage")
    document_id = stored_document(session_factory, storage, pdf_path)
    with session_factory() as db:
        db.add(
            DocumentChunk(
                document_id=document_id,
                chunk_index=0,
                text="stale partial chunk",
                page_number=1,
                token_count=3,
                embedding=[0.0] * 1024,
            )
        )
        db.commit()

    service = DocumentIngestionService(
        session_factory=session_factory,
        storage=storage,
        embedding_service=FailingEmbeddingService(),
    )
    assert service.process_document(document_id) is False

    with session_factory() as db:
        document = db.get(Document, document_id)
        chunk_count = db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        )
        assert document is not None
        assert document.status == DocumentStatus.FAILED
        assert document.error_message is not None
        assert "embedding service" in document.error_message
        assert chunk_count == 0


def test_extraction_failure_marks_failed(tmp_path: Path, make_pdf, session_factory) -> None:
    pdf_path = make_pdf(tmp_path / "blank.pdf", [None])
    storage = DocumentStorage(tmp_path / "storage")
    document_id = stored_document(session_factory, storage, pdf_path)
    service = DocumentIngestionService(
        session_factory=session_factory,
        storage=storage,
        embedding_service=FakeEmbeddingService(),
    )

    assert service.process_document(document_id) is False

    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.status == DocumentStatus.FAILED
        assert document.error_message is not None
        assert "OCR" in document.error_message
