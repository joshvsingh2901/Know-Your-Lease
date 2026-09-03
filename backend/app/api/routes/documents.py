import logging
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    File,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.api.document_access import AccessibleDocument, AccessibleDocuments
from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.schemas.document import (
    DocumentChunkListResponse,
    DocumentChunkResponse,
    DocumentListResponse,
    DocumentResponse,
)
from app.schemas.question import (
    CitationResponse,
    QuestionRequest,
    QuestionResponse,
    RetrievalResponse,
    RetrievedChunkResponse,
)
from app.services.document_ingestion import (
    DocumentIngestionService,
    get_ingestion_service,
)
from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingError,
    EmbeddingProviderError,
)
from app.services.generation import (
    GenerationConfigurationError,
    GenerationError,
    GenerationProviderError,
    GenerationResponseError,
)
from app.services.ingestion_queue import (
    IngestionQueue,
    IngestionQueueError,
    get_ingestion_queue,
)
from app.services.question_answering import (
    DocumentNotFoundError,
    DocumentNotReadyError,
    NoRetrievedEvidenceError,
    QuestionAnsweringService,
    get_question_answering_service,
)
from app.services.storage import (
    DocumentStorage,
    InvalidStorageKeyError,
    StorageError,
    StorageNotFoundError,
    get_document_storage,
)

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)

PDF_SIGNATURE = b"%PDF-"
ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}
QUESTION_SERVICE_EXCEPTIONS = (
    DocumentNotFoundError,
    DocumentNotReadyError,
    NoRetrievedEvidenceError,
    EmbeddingError,
    GenerationError,
)


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    background_tasks: BackgroundTasks,
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
    ingestion_service: Annotated[DocumentIngestionService, Depends(get_ingestion_service)],
    ingestion_queue: Annotated[IngestionQueue | None, Depends(get_ingestion_queue)],
) -> Document:
    filename = Path((file.filename or "").replace("\\", "/")).name
    if not filename:
        raise HTTPException(status_code=400, detail="A PDF file is required.")

    if Path(filename).suffix.lower() != ".pdf":
        raise HTTPException(status_code=415, detail="Only PDF files are supported.")

    if file.content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(status_code=415, detail="Only PDF files are supported.")

    signature = await file.read(len(PDF_SIGNATURE))
    if signature != PDF_SIGNATURE:
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF.")

    file.file.seek(0, 2)
    file_size = file.file.tell()
    if file_size > settings.max_upload_size_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"PDF files must be {settings.max_upload_size_mb} MB or smaller.",
        )

    document_id = uuid.uuid4()
    storage = ingestion_service.storage
    try:
        storage_key = storage.save(document_id, file.file)
    except StorageError as exc:
        logger.warning("Could not store uploaded PDF for document %s", document_id)
        raise HTTPException(
            status_code=500,
            detail="The uploaded PDF could not be stored. Please try again.",
        ) from exc

    document = Document(
        id=document_id,
        original_filename=filename,
        storage_key=storage_key,
        current_ingestion_version=1,
        status=(
            DocumentStatus.QUEUED
            if settings.ingestion_mode == "sqs"
            else DocumentStatus.UPLOADED
        ),
    )
    db.add(document)
    try:
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as exc:
        db.rollback()
        try:
            storage.delete(storage_key)
        except StorageError:
            logger.error("Could not clean up stored PDF for document %s", document_id)
        raise HTTPException(
            status_code=503,
            detail="The document could not be recorded. Please try again.",
        ) from exc
    finally:
        await file.close()

    logger.info("Accepted document upload %s (%d bytes)", document.id, file_size)
    if settings.ingestion_mode == "sqs":
        try:
            if ingestion_queue is None:
                raise IngestionQueueError("The ingestion queue is not configured.")
            ingestion_queue.enqueue(
                document.id,
                document.current_ingestion_version,
            )
        except IngestionQueueError as exc:
            logger.error("Could not enqueue ingestion for document %s", document.id)
            document.status = DocumentStatus.FAILED
            document.error_message = (
                "Document ingestion could not be queued. Please upload the PDF again."
            )
            document.last_ingestion_error_code = "queue_publish_failed"
            document.last_ingestion_failed_at = datetime.now(UTC)
            try:
                db.commit()
            except SQLAlchemyError:
                db.rollback()
                logger.exception(
                    "Could not persist queue failure for document %s", document.id
                )
            raise HTTPException(
                status_code=503,
                detail="The document could not be queued for processing. Please try again.",
            ) from exc
    else:
        background_tasks.add_task(
            ingestion_service.process_document,
            document.id,
            document.current_ingestion_version,
            False,
        )
    return document


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document: AccessibleDocument,
) -> Document:
    return document


@router.get("/documents", response_model=DocumentListResponse)
def list_documents(
    documents: AccessibleDocuments,
) -> DocumentListResponse:
    return DocumentListResponse(
        items=[DocumentResponse.model_validate(document) for document in documents]
    )


@router.get("/documents/{document_id}/pdf", response_class=Response)
def get_document_pdf(
    document: AccessibleDocument,
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
) -> Response:
    if not document.storage_key:
        raise HTTPException(status_code=404, detail="Document PDF is unavailable.")

    try:
        pdf_bytes = storage.read(document.storage_key)
    except (InvalidStorageKeyError, StorageNotFoundError):
        logger.info("Stored PDF is unavailable for document %s", document.id)
        raise HTTPException(status_code=404, detail="Document PDF is unavailable.") from None
    except StorageError:
        logger.warning("Could not retrieve stored PDF for document %s", document.id)
        raise HTTPException(
            status_code=503,
            detail="Document PDF is temporarily unavailable.",
        ) from None
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/documents/{document_id}/chunks",
    response_model=DocumentChunkListResponse,
)
def list_document_chunks(
    document: AccessibleDocument,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentChunkListResponse:
    _require_debug_endpoints()

    total = db.scalar(
        select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.document_id == document.id
        )
    )
    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document.id)
        .order_by(DocumentChunk.chunk_index)
        .offset(offset)
        .limit(limit)
    ).all()
    return DocumentChunkListResponse(
        items=[DocumentChunkResponse.model_validate(chunk) for chunk in chunks],
        total=total or 0,
        limit=limit,
        offset=offset,
    )


def _require_debug_endpoints() -> None:
    if not settings.debug_endpoints_allowed:
        raise HTTPException(status_code=404, detail="Not found.")


def _safe_error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code=status_code, detail={"code": code, "message": message})


def _provider_status(exc: Exception) -> int | None:
    current: BaseException | None = exc
    seen: set[int] = set()
    while isinstance(current, BaseException) and id(current) not in seen:
        seen.add(id(current))
        for attribute in ("http_status", "status_code", "status", "code"):
            value = getattr(current, attribute, None)
            try:
                if value is not None:
                    return int(value)
            except (TypeError, ValueError):
                continue
        current = current.__cause__
    return None


def _question_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DocumentNotFoundError):
        return HTTPException(status_code=404, detail="Document not found.")
    if isinstance(exc, DocumentNotReadyError):
        if exc.status == DocumentStatus.FAILED:
            detail = "This document failed processing and cannot be questioned."
        else:
            detail = "This document is still processing. Wait until it is ready."
        return HTTPException(status_code=409, detail=detail)
    if isinstance(exc, NoRetrievedEvidenceError):
        return HTTPException(
            status_code=409,
            detail="This document has no indexed evidence available.",
        )
    if isinstance(exc, (EmbeddingConfigurationError, GenerationConfigurationError)):
        return _safe_error(
            503,
            "provider_configuration",
            "Question answering is not configured on the server.",
        )
    if isinstance(
        exc,
        (
            EmbeddingProviderError,
            EmbeddingError,
            GenerationProviderError,
            GenerationResponseError,
        ),
    ):
        provider_status = _provider_status(exc)
        if provider_status in {400, 401, 403, 404}:
            return _safe_error(
                503,
                "provider_configuration",
                "Question answering is not configured correctly on the server.",
            )
        if provider_status == 429:
            return _safe_error(
                429,
                "provider_rate_limited",
                "The answer service is temporarily rate-limited. Please try again shortly.",
            )
        if provider_status is not None and 500 <= provider_status <= 599:
            return _safe_error(
                503,
                "provider_temporarily_unavailable",
                "The answer service is temporarily unavailable. Please try again.",
            )
        return _safe_error(
            502,
            "provider_request_failed",
            "The answer service could not complete this request. Please try again.",
        )
    return _safe_error(500, "question_unexpected_error", "Question answering failed unexpectedly.")


@router.post(
    "/documents/{document_id}/retrieve",
    response_model=RetrievalResponse,
)
def retrieve_document_evidence(
    document: AccessibleDocument,
    request: QuestionRequest,
    db: Annotated[Session, Depends(get_db)],
    question_service: Annotated[
        QuestionAnsweringService,
        Depends(get_question_answering_service),
    ],
) -> RetrievalResponse:
    _require_debug_endpoints()
    try:
        results = question_service.retrieve(db, document.id, request.question)
    except QUESTION_SERVICE_EXCEPTIONS as exc:
        raise _question_http_error(exc) from exc
    return RetrievalResponse(
        results=[
            RetrievedChunkResponse(
                chunk_id=result.chunk_id,
                chunk_index=result.chunk_index,
                page_number=result.page_number,
                section_title=result.section_title,
                text=result.text,
                score=result.score,
            )
            for result in results
        ]
    )


@router.post(
    "/documents/{document_id}/questions",
    response_model=QuestionResponse,
)
def ask_document_question(
    document: AccessibleDocument,
    request: QuestionRequest,
    db: Annotated[Session, Depends(get_db)],
    question_service: Annotated[
        QuestionAnsweringService,
        Depends(get_question_answering_service),
    ],
) -> QuestionResponse:
    try:
        result = question_service.answer_question(db, document.id, request.question)
    except QUESTION_SERVICE_EXCEPTIONS as exc:
        raise _question_http_error(exc) from exc
    return QuestionResponse(
        answer=result.answer,
        citations=[
            CitationResponse(
                chunk_id=citation.chunk_id,
                page_number=citation.page_number,
                section_title=citation.section_title,
                snippet=citation.snippet,
                score=citation.score,
            )
            for citation in result.citations
        ],
    )
