import threading
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, sessionmaker

from app.core.database import Base
from app.models.answer_cache import GroundedAnswerCache
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.chunking import ChunkDraft
from app.services.document_ingestion import DocumentIngestionService, IngestionOutcome
from app.services.embeddings import EmbeddingProviderError
from app.services.ingestion_queue import (
    IngestionMessage,
    IngestionQueueConsumer,
    IngestionQueueError,
    ReceivedIngestionMessage,
)
from app.services.pdf_extraction import ExtractedPage
from app.services.storage import DocumentStorage, StorageError, StorageNotFoundError
from app.workers.ingestion import IngestionWorker


class MemoryStorage(DocumentStorage):
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.reads = 0

    def save(self, document_id: uuid.UUID, source: BinaryIO) -> str:
        key = f"uploads/{document_id}.pdf"
        self.objects[key] = source.read()
        return key

    def read(self, storage_key: str) -> bytes:
        self.reads += 1
        return self.objects[storage_key]

    def delete(self, storage_key: str) -> None:
        self.objects.pop(storage_key, None)


class CountingEmbeddingService:
    def __init__(self, failure: Exception | None = None) -> None:
        self.failure = failure
        self.calls = 0

    def embed_documents(
        self,
        texts: list[str],
        token_counts: list[int],
    ) -> list[list[float]]:
        self.calls += 1
        if self.failure is not None:
            raise self.failure
        assert len(texts) == len(token_counts) == 1
        return [[0.5] * 1024]


class RecordingConsumer(IngestionQueueConsumer):
    def __init__(
        self,
        messages: list[ReceivedIngestionMessage],
        *,
        delete_failures: int = 0,
    ) -> None:
        self.messages = messages
        self.delete_failures = delete_failures
        self.deleted: list[str] = []

    def receive(self) -> ReceivedIngestionMessage | None:
        return self.messages.pop(0) if self.messages else None

    def delete(self, receipt_handle: str) -> None:
        if self.delete_failures:
            self.delete_failures -= 1
            raise IngestionQueueError("simulated acknowledgement failure")
        self.deleted.append(receipt_handle)


def add_document(
    session_factory,
    storage: MemoryStorage,
    *,
    status: DocumentStatus = DocumentStatus.QUEUED,
    current_version: int = 1,
    completed_version: int | None = None,
) -> uuid.UUID:
    document_id = uuid.uuid4()
    storage_key = f"uploads/{document_id}.pdf"
    storage.objects[storage_key] = b"%PDF-reliability-test"
    with session_factory() as db:
        db.add(
            Document(
                id=document_id,
                original_filename="lease.pdf",
                storage_key=storage_key,
                status=status,
                current_ingestion_version=current_version,
                completed_ingestion_version=completed_version,
            )
        )
        db.commit()
    return document_id


def add_chunk_and_cache(session_factory, document_id: uuid.UUID, text: str) -> None:
    with session_factory() as db:
        chunk = DocumentChunk(
            document_id=document_id,
            chunk_index=0,
            text=text,
            page_number=1,
            token_count=4,
            embedding=[0.1] * 1024,
        )
        db.add(chunk)
        db.flush()
        db.add(
            GroundedAnswerCache(
                document_id=document_id,
                normalized_question=f"question-{uuid.uuid4()}",
                generation_version="v1",
                answer="cached answer",
                citations=[{"chunk_id": str(chunk.id)}],
            )
        )
        db.commit()


def add_cache(session_factory, document_id: uuid.UUID) -> None:
    with session_factory() as db:
        chunk_id = db.scalar(
            select(DocumentChunk.id).where(DocumentChunk.document_id == document_id)
        )
        assert chunk_id is not None
        db.add(
            GroundedAnswerCache(
                document_id=document_id,
                normalized_question=f"question-{uuid.uuid4()}",
                generation_version="v1",
                answer="cached answer",
                citations=[{"chunk_id": str(chunk_id)}],
            )
        )
        db.commit()


def make_service(
    session_factory,
    storage: MemoryStorage,
    embedding_service: CountingEmbeddingService,
    *,
    indexed_text: str = "new indexed clause",
    extractor=None,
    processing_timeout_seconds: int = 900,
    clock=lambda: datetime.now(UTC),
) -> DocumentIngestionService:
    return DocumentIngestionService(
        session_factory=session_factory,
        storage=storage,
        embedding_service=embedding_service,
        extractor=extractor
        or (lambda _source: [ExtractedPage(page_number=1, text=indexed_text)]),
        chunker=lambda _pages: [
            ChunkDraft(
                chunk_index=0,
                text=indexed_text,
                page_number=1,
                paragraph_index=0,
                section_title=None,
                token_count=4,
            )
        ],
        processing_timeout_seconds=processing_timeout_seconds,
        clock=clock,
    )


def message(document_id: uuid.UUID, ingestion_version: int = 1) -> ReceivedIngestionMessage:
    return ReceivedIngestionMessage(
        body=IngestionMessage(
            document_id=document_id,
            ingestion_version=ingestion_version,
        ).model_dump_json(),
        receipt_handle=f"receipt-{ingestion_version}",
        message_id=f"message-{ingestion_version}",
    )


def test_duplicate_delivery_is_cheap_and_does_not_duplicate_chunks_or_cache_effects(
    session_factory,
) -> None:
    storage = MemoryStorage()
    embedding = CountingEmbeddingService()
    document_id = add_document(session_factory, storage)
    add_chunk_and_cache(session_factory, document_id, "old clause")
    service = make_service(session_factory, storage, embedding)

    assert service.process_document(document_id, 1) == IngestionOutcome.COMPLETED
    add_cache(session_factory, document_id)
    assert service.process_document(document_id, 1) == IngestionOutcome.ALREADY_COMPLETED

    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.status == DocumentStatus.READY
        assert document.completed_ingestion_version == 1
        assert document.ingestion_attempts == 1
        assert db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        ) == 1
        assert db.scalar(
            select(func.count()).select_from(GroundedAnswerCache).where(
                GroundedAnswerCache.document_id == document_id
            )
        ) == 1
    assert embedding.calls == 1
    assert storage.reads == 1


def test_newer_version_wins_and_stale_message_cannot_mutate_chunks_or_cache(
    session_factory,
) -> None:
    storage = MemoryStorage()
    embedding = CountingEmbeddingService()
    document_id = add_document(
        session_factory,
        storage,
        current_version=2,
    )
    add_chunk_and_cache(session_factory, document_id, "version one clause")
    service = make_service(
        session_factory,
        storage,
        embedding,
        indexed_text="version two clause",
    )

    assert service.process_document(document_id, 2) == IngestionOutcome.COMPLETED
    add_cache(session_factory, document_id)
    assert service.process_document(document_id, 1) == IngestionOutcome.STALE

    with session_factory() as db:
        document = db.get(Document, document_id)
        chunks = db.scalars(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.created_at)
        ).all()
        assert document is not None
        assert document.current_ingestion_version == 2
        assert document.completed_ingestion_version == 2
        assert [chunk.text for chunk in chunks] == ["version two clause"]
        assert db.scalar(
            select(func.count()).select_from(GroundedAnswerCache).where(
                GroundedAnswerCache.document_id == document_id
            )
        ) == 1
    assert embedding.calls == 1


def test_inflight_older_attempt_cannot_overwrite_newer_completed_version(
    session_factory,
) -> None:
    storage = MemoryStorage()
    embedding = CountingEmbeddingService()
    document_id = add_document(session_factory, storage, current_version=1)

    def supersede_old_attempt(_source: bytes) -> list[ExtractedPage]:
        with session_factory() as db:
            document = db.get(Document, document_id)
            assert document is not None
            document.current_ingestion_version = 2
            document.completed_ingestion_version = 2
            document.status = DocumentStatus.READY
            db.commit()
        add_chunk_and_cache(session_factory, document_id, "newer committed clause")
        return [ExtractedPage(page_number=1, text="older in-flight clause")]

    old_service = make_service(
        session_factory,
        storage,
        embedding,
        indexed_text="older in-flight clause",
        extractor=supersede_old_attempt,
    )

    assert old_service.process_document(document_id, 1) == IngestionOutcome.STALE

    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.current_ingestion_version == 2
        assert document.completed_ingestion_version == 2
        assert document.status == DocumentStatus.READY
        assert db.scalar(
            select(DocumentChunk.text).where(DocumentChunk.document_id == document_id)
        ) == "newer committed clause"
        assert db.scalar(
            select(func.count()).select_from(GroundedAnswerCache).where(
                GroundedAnswerCache.document_id == document_id
            )
        ) == 1


def test_transient_provider_failure_requeues_and_preserves_committed_data_until_retry(
    session_factory,
) -> None:
    storage = MemoryStorage()
    document_id = add_document(session_factory, storage)
    add_chunk_and_cache(session_factory, document_id, "previous committed clause")
    transient_embedding = CountingEmbeddingService(
        EmbeddingProviderError(
            "provider unavailable",
            transient=True,
            error_code="provider_rate_limit",
        )
    )
    failing_service = make_service(session_factory, storage, transient_embedding)

    assert (
        failing_service.process_document(document_id, 1)
        == IngestionOutcome.RETRYABLE_FAILURE
    )
    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.status == DocumentStatus.QUEUED
        assert document.last_ingestion_error_code == "provider_rate_limit"
        assert document.ingestion_attempts == 1
        assert db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        ) == 1
        assert db.scalar(
            select(func.count()).select_from(GroundedAnswerCache).where(
                GroundedAnswerCache.document_id == document_id
            )
        ) == 1

    successful_embedding = CountingEmbeddingService()
    retry_service = make_service(session_factory, storage, successful_embedding)
    assert retry_service.process_document(document_id, 1) == IngestionOutcome.COMPLETED
    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.status == DocumentStatus.READY
        assert document.ingestion_attempts == 2
        assert db.scalar(
            select(func.count()).select_from(GroundedAnswerCache).where(
                GroundedAnswerCache.document_id == document_id
            )
        ) == 0


def test_inline_mode_without_durable_redelivery_marks_interrupted_attempt_failed(
    session_factory,
) -> None:
    storage = MemoryStorage()
    document_id = add_document(
        session_factory,
        storage,
        status=DocumentStatus.UPLOADED,
    )
    transient_embedding = CountingEmbeddingService(
        EmbeddingProviderError("provider unavailable", transient=True)
    )
    service = make_service(session_factory, storage, transient_embedding)

    assert (
        service.process_document(document_id, 1, durable_retries=False)
        == IngestionOutcome.TERMINAL_FAILURE
    )
    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.status == DocumentStatus.FAILED
        assert document.last_ingestion_error_code == "provider_unavailable"


def test_final_transaction_failure_rolls_back_chunks_cache_and_ready_state(
    session_factory,
) -> None:
    storage = MemoryStorage()
    document_id = add_document(session_factory, storage)
    add_chunk_and_cache(session_factory, document_id, "previous committed clause")
    engine = session_factory.kw["bind"]
    failure_state = {"pending": True}

    class FailFinalCommitSession(Session):
        def commit(self) -> None:
            if failure_state["pending"] and any(
                isinstance(item, DocumentChunk) for item in self.new
            ):
                failure_state["pending"] = False
                raise SQLAlchemyError("simulated final transaction failure")
            super().commit()

    failing_factory = sessionmaker(
        bind=engine,
        class_=FailFinalCommitSession,
        autoflush=False,
        expire_on_commit=False,
    )
    service = make_service(
        failing_factory,
        storage,
        CountingEmbeddingService(),
    )

    assert service.process_document(document_id, 1) == IngestionOutcome.RETRYABLE_FAILURE

    with session_factory() as db:
        document = db.get(Document, document_id)
        chunks = db.scalars(
            select(DocumentChunk).where(DocumentChunk.document_id == document_id)
        ).all()
        assert document is not None
        assert document.status == DocumentStatus.QUEUED
        assert document.completed_ingestion_version is None
        assert document.last_ingestion_error_code == "database_error"
        assert [chunk.text for chunk in chunks] == ["previous committed clause"]
        assert db.scalar(
            select(func.count()).select_from(GroundedAnswerCache).where(
                GroundedAnswerCache.document_id == document_id
            )
        ) == 1


def test_crash_after_claim_is_reclaimed_after_processing_timeout(session_factory) -> None:
    class SimulatedWorkerCrash(BaseException):
        pass

    started_at = datetime(2026, 9, 3, tzinfo=UTC)
    storage = MemoryStorage()
    document_id = add_document(session_factory, storage)

    def crash_after_claim(_source: bytes):
        raise SimulatedWorkerCrash

    crashing_service = make_service(
        session_factory,
        storage,
        CountingEmbeddingService(),
        extractor=crash_after_claim,
        processing_timeout_seconds=60,
        clock=lambda: started_at,
    )

    with pytest.raises(SimulatedWorkerCrash):
        crashing_service.process_document(document_id, 1)
    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.status == DocumentStatus.PROCESSING
        assert document.ingestion_attempts == 1

    recovery_service = make_service(
        session_factory,
        storage,
        CountingEmbeddingService(),
        processing_timeout_seconds=60,
        clock=lambda: started_at + timedelta(seconds=61),
    )
    assert recovery_service.process_document(document_id, 1) == IngestionOutcome.COMPLETED
    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.status == DocumentStatus.READY
        assert document.ingestion_attempts == 2


def test_commit_then_ack_failure_redelivery_is_noop_and_acknowledged(
    session_factory,
) -> None:
    storage = MemoryStorage()
    embedding = CountingEmbeddingService()
    document_id = add_document(session_factory, storage)
    received = message(document_id)
    consumer = RecordingConsumer(
        [received, received],
        delete_failures=1,
    )
    worker = IngestionWorker(
        consumer=consumer,
        ingestion_service=make_service(session_factory, storage, embedding),
    )

    worker.run_once()
    assert consumer.deleted == []
    worker.run_once()

    assert consumer.deleted == ["receipt-1"]
    assert embedding.calls == 1
    with session_factory() as db:
        assert db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        ) == 1


def test_atomic_claim_prevents_concurrent_duplicate_processing(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'concurrency.db'}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    storage = MemoryStorage()
    document_id = add_document(factory, storage)
    embedding_started = threading.Event()
    release_embedding = threading.Event()

    class BlockingEmbeddingService(CountingEmbeddingService):
        def embed_documents(self, texts, token_counts):
            embedding_started.set()
            assert release_embedding.wait(timeout=5)
            return super().embed_documents(texts, token_counts)

    first_embedding = BlockingEmbeddingService()
    first_service = make_service(factory, storage, first_embedding)
    second_embedding = CountingEmbeddingService()
    second_service = make_service(factory, storage, second_embedding)
    first_outcomes: list[IngestionOutcome] = []
    first_thread = threading.Thread(
        target=lambda: first_outcomes.append(first_service.process_document(document_id, 1))
    )

    first_thread.start()
    assert embedding_started.wait(timeout=5)
    assert second_service.process_document(document_id, 1) == IngestionOutcome.BUSY
    release_embedding.set()
    first_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert first_outcomes == [IngestionOutcome.COMPLETED]
    assert first_embedding.calls == 1
    assert second_embedding.calls == 0
    with factory() as db:
        assert db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        ) == 1
    Base.metadata.drop_all(engine)
    engine.dispose()


class RaisingStorage(DocumentStorage):
    def __init__(self, error: Exception) -> None:
        self.error = error

    def save(self, document_id: uuid.UUID, source: BinaryIO) -> str:
        raise NotImplementedError

    def read(self, storage_key: str) -> bytes:
        raise self.error

    def delete(self, storage_key: str) -> None:
        pass


def test_transient_storage_error_is_retryable_but_missing_object_is_terminal(
    session_factory,
) -> None:
    storage = MemoryStorage()
    document_id = add_document(session_factory, storage)

    transient_service = make_service(
        session_factory,
        RaisingStorage(StorageError("storage backend unavailable")),
        CountingEmbeddingService(),
    )
    assert (
        transient_service.process_document(document_id, 1)
        == IngestionOutcome.RETRYABLE_FAILURE
    )
    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.status == DocumentStatus.QUEUED
        assert document.last_ingestion_error_code == "storage_unavailable"

    missing_service = make_service(
        session_factory,
        RaisingStorage(StorageNotFoundError("stored object is gone")),
        CountingEmbeddingService(),
    )
    assert (
        missing_service.process_document(document_id, 1)
        == IngestionOutcome.TERMINAL_FAILURE
    )
    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.status == DocumentStatus.FAILED
        assert document.last_ingestion_error_code == "storage_missing"


def test_worker_acknowledges_a_recorded_terminal_failure(session_factory) -> None:
    storage = MemoryStorage()
    document_id = add_document(session_factory, storage)
    service = make_service(
        session_factory,
        RaisingStorage(StorageNotFoundError("stored object is gone")),
        CountingEmbeddingService(),
    )
    consumer = RecordingConsumer([message(document_id)])
    worker = IngestionWorker(consumer=consumer, ingestion_service=service)

    worker.run_once()

    assert consumer.deleted == ["receipt-1"]
    with session_factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        assert document.status == DocumentStatus.FAILED


def test_atomic_claim_prevents_concurrent_duplicate_reclaim(tmp_path: Path) -> None:
    engine = create_engine(
        f"sqlite+pysqlite:///{tmp_path / 'reclaim.db'}",
        connect_args={"check_same_thread": False},
    )
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.create_all(engine)
    storage = MemoryStorage()
    document_id = add_document(factory, storage, status=DocumentStatus.PROCESSING)
    with factory() as db:
        document = db.get(Document, document_id)
        assert document is not None
        document.last_ingestion_started_at = datetime(2020, 1, 1, tzinfo=UTC)
        document.ingestion_attempts = 1
        db.commit()

    embedding_started = threading.Event()
    release_embedding = threading.Event()

    class BlockingEmbeddingService(CountingEmbeddingService):
        def embed_documents(self, texts, token_counts):
            embedding_started.set()
            assert release_embedding.wait(timeout=5)
            return super().embed_documents(texts, token_counts)

    first_embedding = BlockingEmbeddingService()
    first_service = make_service(
        factory, storage, first_embedding, processing_timeout_seconds=60
    )
    second_embedding = CountingEmbeddingService()
    second_service = make_service(
        factory, storage, second_embedding, processing_timeout_seconds=60
    )
    first_outcomes: list[IngestionOutcome] = []
    first_thread = threading.Thread(
        target=lambda: first_outcomes.append(first_service.process_document(document_id, 1))
    )

    first_thread.start()
    assert embedding_started.wait(timeout=5)
    assert second_service.process_document(document_id, 1) == IngestionOutcome.BUSY
    release_embedding.set()
    first_thread.join(timeout=5)

    assert not first_thread.is_alive()
    assert first_outcomes == [IngestionOutcome.COMPLETED]
    assert first_embedding.calls == 1
    assert second_embedding.calls == 0
    with factory() as db:
        assert db.scalar(
            select(func.count()).select_from(DocumentChunk).where(
                DocumentChunk.document_id == document_id
            )
        ) == 1
    Base.metadata.drop_all(engine)
    engine.dispose()
