from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.schemas.document import DocumentResponse

router = APIRouter(tags=["documents"])

PDF_SIGNATURE = b"%PDF-"
ALLOWED_CONTENT_TYPES = {"application/pdf", "application/x-pdf"}


@router.post(
    "/documents",
    response_model=DocumentResponse,
    status_code=status.HTTP_201_CREATED,
)
async def upload_document(
    file: Annotated[UploadFile, File()],
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    filename = Path(file.filename or "").name
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

    document = Document(original_filename=filename, status=DocumentStatus.UPLOADED)
    db.add(document)
    try:
        db.commit()
        db.refresh(document)
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="The document could not be recorded. Please try again.",
        ) from exc
    finally:
        await file.close()

    return document
