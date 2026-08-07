import logging
import uuid
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
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.schemas.document import (
    DocumentChunkListResponse,
    DocumentChunkResponse,
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
from app.services.question_answering import (
    DocumentNotFoundError,
    DocumentNotReadyError,
    NoRetrievedEvidenceError,
    QuestionAnsweringService,
    get_question_answering_service,
)
from app.services.storage import DocumentStorage, StorageError, get_document_storage

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
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    document = Document(
        id=document_id,
        original_filename=filename,
        storage_key=storage_key,
        status=DocumentStatus.UPLOADED,
    )
    db.add(document)
    try:
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as exc:
        db.rollback()
        storage.delete(storage_key)
        raise HTTPException(
            status_code=503,
            detail="The document could not be recorded. Please try again.",
        ) from exc
    finally:
        await file.close()

    logger.info("Accepted document upload %s (%d bytes)", document.id, file_size)
    background_tasks.add_task(ingestion_service.process_document, document.id)
    return document


@router.get("/documents/{document_id}", response_model=DocumentResponse)
def get_document(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


@router.get("/documents/{document_id}/pdf", response_class=FileResponse)
def get_document_pdf(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    storage: Annotated[DocumentStorage, Depends(get_document_storage)],
) -> FileResponse:
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    if not document.storage_key:
        raise HTTPException(status_code=404, detail="Document PDF is unavailable.")

    try:
        pdf_path = storage.resolve(document.storage_key)
    except StorageError:
        logger.warning("Invalid PDF storage key for document %s", document_id)
        raise HTTPException(status_code=404, detail="Document PDF is unavailable.") from None

    if not pdf_path.is_file():
        logger.info("Stored PDF is unavailable for document %s", document_id)
        raise HTTPException(status_code=404, detail="Document PDF is unavailable.")
    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={"Cache-Control": "no-store"},
    )


@router.get(
    "/documents/{document_id}/chunks",
    response_model=DocumentChunkListResponse,
)
def list_document_chunks(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> DocumentChunkListResponse:
    if db.get(Document, document_id) is None:
        raise HTTPException(status_code=404, detail="Document not found.")

    total = db.scalar(
        select(func.count()).select_from(DocumentChunk).where(
            DocumentChunk.document_id == document_id
        )
    )
    chunks = db.scalars(
        select(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
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
        return HTTPException(
            status_code=503,
            detail="Question answering is not configured on the server.",
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
        return HTTPException(
            status_code=502,
            detail="The question service could not complete this request. Please try again.",
        )
    return HTTPException(status_code=500, detail="Question answering failed unexpectedly.")


@router.post(
    "/documents/{document_id}/retrieve",
    response_model=RetrievalResponse,
)
def retrieve_document_evidence(
    document_id: uuid.UUID,
    request: QuestionRequest,
    db: Annotated[Session, Depends(get_db)],
    question_service: Annotated[
        QuestionAnsweringService,
        Depends(get_question_answering_service),
    ],
) -> RetrievalResponse:
    try:
        results = question_service.retrieve(db, document_id, request.question)
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
    document_id: uuid.UUID,
    request: QuestionRequest,
    db: Annotated[Session, Depends(get_db)],
    question_service: Annotated[
        QuestionAnsweringService,
        Depends(get_question_answering_service),
    ],
) -> QuestionResponse:
    try:
        result = question_service.answer_question(db, document_id, request.question)
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
