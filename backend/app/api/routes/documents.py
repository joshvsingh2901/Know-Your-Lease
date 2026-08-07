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
from app.services.document_ingestion import (
    DocumentIngestionService,
    get_ingestion_service,
)
from app.services.storage import StorageError

router = APIRouter(tags=["documents"])
logger = logging.getLogger(__name__)

PDF_SIGNATURE = b"%PDF-"
ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


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
