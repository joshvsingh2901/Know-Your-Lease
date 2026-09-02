import uuid
from typing import BinaryIO

from sqlalchemy import select

from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.chunking import ChunkDraft
from app.services.document_ingestion import DocumentIngestionService
from app.services.ingestion_queue import (
    IngestionMessage,
    IngestionQueueConsumer,
    ReceivedIngestionMessage,
)
from app.services.pdf_extraction import ExtractedPage
from app.services.storage import DocumentStorage
from app.workers.ingestion import IngestionWorker


class MemoryStorage(DocumentStorage):
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.read_keys: list[str] = []

    def save(self, document_id: uuid.UUID, source: BinaryIO) -> str:
        key = f"uploads/{document_id}.pdf"
        self.objects[key] = source.read()
        return key

    def read(self, storage_key: str) -> bytes:
        self.read_keys.append(storage_key)
        return self.objects[storage_key]

    def delete(self, storage_key: str) -> None:
        self.objects.pop(storage_key, None)


class FakeEmbeddingService:
    def embed_documents(
        self, texts: list[str], token_counts: list[int]
    ) -> list[list[float]]:
        assert texts == ["The tenant must pay rent."]
        assert token_counts == [6]
        return [[0.25] * 1024]


class FakeConsumer(IngestionQueueConsumer):
    def __init__(self, messages: list[ReceivedIngestionMessage]) -> None:
        self.messages = messages
        self.deleted_receipts: list[str] = []

    def receive(self) -> ReceivedIngestionMessage | None:
        return self.messages.pop(0) if self.messages else None

    def delete(self, receipt_handle: str) -> None:
        self.deleted_receipts.append(receipt_handle)


class StubIngestionService:
    def __init__(self, result: bool) -> None:
        self.result = result
        self.document_ids: list[uuid.UUID] = []

    def process_document(self, document_id: uuid.UUID) -> bool:
        self.document_ids.append(document_id)
        return self.result


def queued_message(document_id: uuid.UUID, *, body: str | None = None):
    return ReceivedIngestionMessage(
        body=body or IngestionMessage(document_id=document_id).model_dump_json(),
        receipt_handle="receipt-handle",
        message_id="message-id",
    )


def test_worker_runs_existing_ingestion_with_storage_and_acknowledges_success(
    session_factory,
) -> None:
    document_id = uuid.uuid4()
    storage_key = f"uploads/{document_id}.pdf"
    storage = MemoryStorage({storage_key: b"%PDF-from-storage-abstraction"})
    with session_factory() as db:
        db.add(
            Document(
                id=document_id,
                original_filename="lease.pdf",
                storage_key=storage_key,
                status=DocumentStatus.QUEUED,
            )
        )
        db.commit()

    def extract(source: bytes) -> list[ExtractedPage]:
        assert source == b"%PDF-from-storage-abstraction"
        with session_factory() as db:
            document = db.get(Document, document_id)
            assert document is not None
            assert document.status == DocumentStatus.PROCESSING
        return [ExtractedPage(page_number=1, text="The tenant must pay rent.")]

    service = DocumentIngestionService(
        session_factory=session_factory,
        storage=storage,
        embedding_service=FakeEmbeddingService(),
        extractor=extract,
        chunker=lambda _pages: [
            ChunkDraft(
                chunk_index=0,
                text="The tenant must pay rent.",
                page_number=1,
                paragraph_index=0,
                section_title=None,
                token_count=6,
            )
        ],
    )
    consumer = FakeConsumer([queued_message(document_id)])
    worker = IngestionWorker(
        consumer=consumer,
        ingestion_service=service,
        session_factory=session_factory,
    )

    worker.run_once()

    with session_factory() as db:
        document = db.get(Document, document_id)
        chunks = db.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        ).all()
        assert document is not None
        assert document.status == DocumentStatus.READY
        assert len(chunks) == 1
    assert storage.read_keys == [storage_key]
    assert consumer.deleted_receipts == ["receipt-handle"]


def test_worker_does_not_acknowledge_failed_ingestion(session_factory) -> None:
    document_id = uuid.uuid4()
    with session_factory() as db:
        db.add(Document(id=document_id, original_filename="lease.pdf"))
        db.commit()
    service = StubIngestionService(False)
    consumer = FakeConsumer([queued_message(document_id)])
    worker = IngestionWorker(
        consumer=consumer,
        ingestion_service=service,
        session_factory=session_factory,
    )

    worker.run_once()

    assert service.document_ids == [document_id]
    assert consumer.deleted_receipts == []


def test_worker_handles_malformed_message_without_acknowledging(session_factory) -> None:
    service = StubIngestionService(True)
    consumer = FakeConsumer(
        [queued_message(uuid.uuid4(), body='{"version":2,"document_id":"secret"}')]
    )
    worker = IngestionWorker(
        consumer=consumer,
        ingestion_service=service,
        session_factory=session_factory,
    )

    worker.run_once()

    assert service.document_ids == []
    assert consumer.deleted_receipts == []


def test_worker_handles_missing_document_without_acknowledging(session_factory) -> None:
    service = StubIngestionService(True)
    consumer = FakeConsumer([queued_message(uuid.uuid4())])
    worker = IngestionWorker(
        consumer=consumer,
        ingestion_service=service,
        session_factory=session_factory,
    )

    worker.run_once()

    assert service.document_ids == []
    assert consumer.deleted_receipts == []
