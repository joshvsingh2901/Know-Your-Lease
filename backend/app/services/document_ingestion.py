import logging
import uuid
from collections.abc import Callable
from functools import lru_cache

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.chunking import ChunkDraft, chunk_pages
from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingError,
    EmbeddingProviderError,
    VoyageEmbeddingService,
)
from app.services.pdf_extraction import PDFExtractionError, extract_pdf_pages
from app.services.storage import DocumentStorage, StorageError
from app.services.text_normalization import normalize_page_text

logger = logging.getLogger(__name__)

SessionFactory = Callable[[], Session]


class DocumentIngestionService:
    def __init__(
        self,
        *,
        session_factory: SessionFactory = SessionLocal,
        storage: DocumentStorage | None = None,
        embedding_service: VoyageEmbeddingService | None = None,
        extractor: Callable = extract_pdf_pages,
        chunker: Callable[[list], list[ChunkDraft]] = chunk_pages,
    ) -> None:
        self.session_factory = session_factory
        self.storage = storage or DocumentStorage()
        self.embedding_service = embedding_service or VoyageEmbeddingService()
        self.extractor = extractor
        self.chunker = chunker

    def process_document(self, document_id: uuid.UUID) -> bool:
        try:
            storage_key = self._mark_processing(document_id)
            path = self.storage.resolve(storage_key)
            logger.info("Starting extraction for document %s", document_id)
            extracted_pages = self.extractor(path)
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
            self._store_completed_index(document_id, drafts, vectors)
            logger.info("Document %s indexing completed successfully", document_id)
            return True
        except Exception as exc:  # noqa: BLE001 - background job failure boundary
            message = self._safe_error_message(exc)
            logger.error("Document %s indexing failed: %s", document_id, message)
            self._mark_failed(document_id, message)
            return False

    def _mark_processing(self, document_id: uuid.UUID) -> str:
        with self.session_factory() as db:
            document = db.get(Document, document_id)
            if document is None:
                raise ValueError("The document does not exist.")
            if not document.storage_key:
                raise StorageError("The document has no stored PDF.")
            document.status = DocumentStatus.PROCESSING
            document.error_message = None
            db.commit()
            return document.storage_key

    def _store_completed_index(
        self,
        document_id: uuid.UUID,
        drafts: list[ChunkDraft],
        vectors: list[list[float]],
    ) -> None:
        with self.session_factory() as db:
            document = db.get(Document, document_id)
            if document is None:
                raise ValueError("The document does not exist.")
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
            document.status = DocumentStatus.READY
            document.error_message = None
            db.commit()

    def _mark_failed(self, document_id: uuid.UUID, message: str) -> None:
        try:
            with self.session_factory() as db:
                document = db.get(Document, document_id)
                if document is None:
                    return
                db.execute(delete(DocumentChunk).where(DocumentChunk.document_id == document_id))
                document.status = DocumentStatus.FAILED
                document.error_message = message[:500]
                db.commit()
        except Exception:
            logger.exception("Could not persist failed status for document %s", document_id)

    @staticmethod
    def _safe_error_message(exc: Exception) -> str:
        if isinstance(exc, (PDFExtractionError, StorageError, EmbeddingConfigurationError)):
            return str(exc)
        if isinstance(exc, (EmbeddingProviderError, EmbeddingError)):
            return "The embedding service could not index this document. Please try again later."
        return "Document processing failed. Please try again or upload a different PDF."


@lru_cache(maxsize=1)
def get_ingestion_service() -> DocumentIngestionService:
    return DocumentIngestionService()
