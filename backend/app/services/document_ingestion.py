import enum
import logging
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from functools import lru_cache

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal
from app.models.answer_cache import GroundedAnswerCache
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.chunking import ChunkDraft, chunk_pages
from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingError,
    EmbeddingProviderError,
    VoyageEmbeddingService,
    get_embedding_service,
)
from app.services.pdf_extraction import PDFExtractionError, extract_pdf_pages
from app.services.storage import (
    DocumentStorage,
    InvalidStorageKeyError,
    StorageError,
    StorageNotFoundError,
    get_document_storage,
)
from app.services.text_normalization import normalize_page_text

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class IngestionOutcome(str, enum.Enum):
    COMPLETED = "completed"
    ALREADY_COMPLETED = "already_completed"
    STALE = "stale"
    RETRYABLE_FAILURE = "retryable_failure"
    TERMINAL_FAILURE = "terminal_failure"
    BUSY = "busy"
    MISSING = "missing"
    FUTURE = "future"

    @property
    def acknowledge(self) -> bool:
        return self in {
            IngestionOutcome.COMPLETED,
            IngestionOutcome.ALREADY_COMPLETED,
            IngestionOutcome.STALE,
            IngestionOutcome.TERMINAL_FAILURE,
        }


@dataclass(frozen=True)
class _IngestionClaim:
    outcome: IngestionOutcome | None = None
    storage_key: str | None = None
    attempt: int | None = None


@dataclass(frozen=True)
class _IngestionFailure:
    outcome: IngestionOutcome
    error_code: str
    message: str


class DocumentIngestionService:
    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        storage: DocumentStorage | None = None,
        embedding_service: VoyageEmbeddingService | None = None,
        extractor: Callable = extract_pdf_pages,
        chunker: Callable[[list], list[ChunkDraft]] = chunk_pages,
        processing_timeout_seconds: int | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage or get_document_storage()
        self.embedding_service = embedding_service or get_embedding_service()
        self.extractor = extractor
        self.chunker = chunker
        self.processing_timeout_seconds = (
            settings.ingestion_processing_timeout_seconds
            if processing_timeout_seconds is None
            else processing_timeout_seconds
        )
        self.clock = clock

    def process_document(
        self,
        document_id: uuid.UUID,
        ingestion_version: int = 1,
        durable_retries: bool = True,
    ) -> IngestionOutcome:
        try:
            claim = self._claim(document_id, ingestion_version)
        except SQLAlchemyError:
            logger.exception(
                "Could not claim ingestion version %d for document %s",
                ingestion_version,
                document_id,
            )
            return IngestionOutcome.RETRYABLE_FAILURE

        if claim.outcome is not None:
            return claim.outcome
        if claim.storage_key is None or claim.attempt is None:
            logger.error("Ingestion claim for document %s was incomplete", document_id)
            return IngestionOutcome.RETRYABLE_FAILURE

        try:
            pdf_bytes = self.storage.read(claim.storage_key)
            logger.info(
                "Starting extraction for document %s ingestion_version=%d attempt=%d",
                document_id,
                ingestion_version,
                claim.attempt,
            )
            extracted_pages = self.extractor(pdf_bytes)
            pages = [
                type(page)(page_number=page.page_number, text=normalize_page_text(page.text))
                for page in extracted_pages
            ]
            logger.info("Extracted %d pages for document %s", len(pages), document_id)

            drafts = self.chunker(pages)
            if not drafts:
                raise PDFExtractionError("No useful text chunks could be created from this PDF.")
            logger.info("Created %d chunks for document %s", len(drafts), document_id)

            vectors = self.embedding_service.embed_documents(
                [draft.text for draft in drafts],
                [draft.token_count for draft in drafts],
            )
            outcome = self._store_completed_index(
                document_id,
                ingestion_version,
                claim.attempt,
                drafts,
                vectors,
            )
            if outcome == IngestionOutcome.COMPLETED:
                logger.info(
                    "Document %s ingestion version %d completed successfully",
                    document_id,
                    ingestion_version,
                )
            return outcome
        except Exception as exc:  # noqa: BLE001 - durable job failure boundary
            failure = self._classify_failure(exc)
            if (
                failure.outcome == IngestionOutcome.RETRYABLE_FAILURE
                and not durable_retries
            ):
                failure = _IngestionFailure(
                    IngestionOutcome.TERMINAL_FAILURE,
                    failure.error_code,
                    "Document processing was interrupted. Please try uploading again.",
                )
            logger.error(
                "Document %s ingestion version %d failed code=%s retryable=%s",
                document_id,
                ingestion_version,
                failure.error_code,
                failure.outcome == IngestionOutcome.RETRYABLE_FAILURE,
            )
            return self._record_failure(
                document_id,
                ingestion_version,
                claim.attempt,
                failure,
            )

    def _claim(
        self,
        document_id: uuid.UUID,
        ingestion_version: int,
    ) -> _IngestionClaim:
        now = self.clock()
        stale_before = now - timedelta(seconds=self.processing_timeout_seconds)
        with self.session_factory() as db:
            document = db.get(Document, document_id)
            if document is None:
                return _IngestionClaim(outcome=IngestionOutcome.MISSING)

            existing_outcome = self._non_claimable_outcome(document, ingestion_version)
            if existing_outcome is not None:
                return _IngestionClaim(outcome=existing_outcome)

            if not document.storage_key:
                document.status = DocumentStatus.FAILED
                document.error_message = "The document has no stored PDF."
                document.last_ingestion_error_code = "storage_missing"
                document.last_ingestion_failed_at = now
                db.commit()
                return _IngestionClaim(outcome=IngestionOutcome.TERMINAL_FAILURE)

            claimable_status = or_(
                Document.status.in_([DocumentStatus.UPLOADED, DocumentStatus.QUEUED]),
                and_(
                    Document.status == DocumentStatus.PROCESSING,
                    or_(
                        Document.last_ingestion_started_at.is_(None),
                        Document.last_ingestion_started_at <= stale_before,
                    ),
                ),
            )
            result = db.execute(
                update(Document)
                .where(
                    Document.id == document_id,
                    Document.current_ingestion_version == ingestion_version,
                    or_(
                        Document.completed_ingestion_version.is_(None),
                        Document.completed_ingestion_version != ingestion_version,
                    ),
                    claimable_status,
                )
                .values(
                    status=DocumentStatus.PROCESSING,
                    error_message=None,
                    ingestion_attempts=Document.ingestion_attempts + 1,
                    last_ingestion_started_at=now,
                )
                .returning(Document.storage_key, Document.ingestion_attempts)
                .execution_options(synchronize_session=False)
            ).one_or_none()
            if result is not None:
                db.commit()
                return _IngestionClaim(
                    storage_key=result.storage_key,
                    attempt=result.ingestion_attempts,
                )

            db.rollback()
            current = db.get(Document, document_id)
            if current is None:
                return _IngestionClaim(outcome=IngestionOutcome.MISSING)
            return _IngestionClaim(
                outcome=self._non_claimable_outcome(current, ingestion_version)
                or IngestionOutcome.BUSY
            )

    @staticmethod
    def _non_claimable_outcome(
        document: Document,
        ingestion_version: int,
    ) -> IngestionOutcome | None:
        if ingestion_version < document.current_ingestion_version:
            return IngestionOutcome.STALE
        if ingestion_version > document.current_ingestion_version:
            return IngestionOutcome.FUTURE
        if (
            document.status == DocumentStatus.READY
            and document.completed_ingestion_version == ingestion_version
        ):
            return IngestionOutcome.ALREADY_COMPLETED
        if document.status == DocumentStatus.FAILED:
            return IngestionOutcome.TERMINAL_FAILURE
        if document.status == DocumentStatus.READY:
            return IngestionOutcome.BUSY
        return None

    def _store_completed_index(
        self,
        document_id: uuid.UUID,
        ingestion_version: int,
        attempt: int,
        drafts: list[ChunkDraft],
        vectors: list[list[float]],
    ) -> IngestionOutcome:
        with self.session_factory() as db:
            document = db.scalar(
                select(Document).where(Document.id == document_id).with_for_update()
            )
            if document is None:
                return IngestionOutcome.MISSING
            if ingestion_version < document.current_ingestion_version:
                return IngestionOutcome.STALE
            if ingestion_version > document.current_ingestion_version:
                return IngestionOutcome.FUTURE
            if (
                document.status == DocumentStatus.READY
                and document.completed_ingestion_version == ingestion_version
            ):
                return IngestionOutcome.ALREADY_COMPLETED
            if document.ingestion_attempts != attempt:
                return IngestionOutcome.BUSY
            if document.status != DocumentStatus.PROCESSING:
                return IngestionOutcome.BUSY

            db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
            db.add_all(
                DocumentChunk(
                    document_id=document_id,
                    chunk_index=draft.chunk_index,
                    text=draft.text,
                    page_number=draft.page_number,
                    paragraph_index=draft.paragraph_index,
                    section_title=draft.section_title,
                    token_count=draft.token_count,
                    embedding=vector,
                )
                for draft, vector in zip(drafts, vectors, strict=True)
            )
            db.execute(
                delete(GroundedAnswerCache).where(
                    GroundedAnswerCache.document_id == document_id
                )
            )
            document.status = DocumentStatus.READY
            document.completed_ingestion_version = ingestion_version
            document.error_message = None
            db.commit()
            return IngestionOutcome.COMPLETED

    def _record_failure(
        self,
        document_id: uuid.UUID,
        ingestion_version: int,
        attempt: int,
        failure: _IngestionFailure,
    ) -> IngestionOutcome:
        try:
            with self.session_factory() as db:
                document = db.scalar(
                    select(Document).where(Document.id == document_id).with_for_update()
                )
                if document is None:
                    return IngestionOutcome.MISSING
                if ingestion_version < document.current_ingestion_version:
                    return IngestionOutcome.STALE
                if ingestion_version > document.current_ingestion_version:
                    return IngestionOutcome.FUTURE
                if (
                    document.status == DocumentStatus.READY
                    and document.completed_ingestion_version == ingestion_version
                ):
                    return IngestionOutcome.ALREADY_COMPLETED
                if document.ingestion_attempts != attempt:
                    return IngestionOutcome.BUSY

                document.status = (
                    DocumentStatus.QUEUED
                    if failure.outcome == IngestionOutcome.RETRYABLE_FAILURE
                    else DocumentStatus.FAILED
                )
                document.error_message = failure.message[:500]
                document.last_ingestion_error_code = failure.error_code
                document.last_ingestion_failed_at = self.clock()
                db.commit()
                return failure.outcome
        except SQLAlchemyError:
            logger.exception(
                "Could not persist ingestion failure metadata for document %s",
                document_id,
            )
            return IngestionOutcome.RETRYABLE_FAILURE

    @staticmethod
    def _classify_failure(exc: Exception) -> _IngestionFailure:
        if isinstance(exc, PDFExtractionError):
            return _IngestionFailure(
                IngestionOutcome.TERMINAL_FAILURE,
                "invalid_pdf",
                str(exc),
            )
        if isinstance(exc, (StorageNotFoundError, InvalidStorageKeyError)):
            return _IngestionFailure(
                IngestionOutcome.TERMINAL_FAILURE,
                "storage_missing",
                "The stored PDF is unavailable.",
            )
        if isinstance(exc, StorageError):
            return _IngestionFailure(
                IngestionOutcome.RETRYABLE_FAILURE,
                "storage_unavailable",
                "Document storage is temporarily unavailable. Processing will retry.",
            )
        if isinstance(exc, EmbeddingConfigurationError):
            return _IngestionFailure(
                IngestionOutcome.TERMINAL_FAILURE,
                "provider_configuration",
                "Document indexing is not configured correctly.",
            )
        if isinstance(exc, EmbeddingProviderError):
            return _IngestionFailure(
                (
                    IngestionOutcome.RETRYABLE_FAILURE
                    if exc.transient
                    else IngestionOutcome.TERMINAL_FAILURE
                ),
                exc.error_code,
                (
                    "The embedding service is temporarily unavailable. Processing will retry."
                    if exc.transient
                    else "The embedding service could not index this document."
                ),
            )
        if isinstance(exc, EmbeddingError):
            return _IngestionFailure(
                IngestionOutcome.TERMINAL_FAILURE,
                "embedding_error",
                "The document could not be embedded safely.",
            )
        if isinstance(exc, SQLAlchemyError):
            return _IngestionFailure(
                IngestionOutcome.RETRYABLE_FAILURE,
                "database_error",
                "Database persistence is temporarily unavailable. Processing will retry.",
            )
        return _IngestionFailure(
            IngestionOutcome.TERMINAL_FAILURE,
            "unknown",
            "Document processing failed. Please try again or upload a different PDF.",
        )


@lru_cache(maxsize=1)
def get_ingestion_service() -> DocumentIngestionService:
    return DocumentIngestionService()
