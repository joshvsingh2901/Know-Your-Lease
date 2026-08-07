import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.document import DocumentStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    filename: str = Field(validation_alias="original_filename")
    status: DocumentStatus
    created_at: datetime
    updated_at: datetime
    error_message: str | None


class DocumentListResponse(BaseModel):
    items: list[DocumentResponse]


class DocumentChunkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    chunk_index: int
    page_number: int
    paragraph_index: int | None
    section_title: str | None
    token_count: int
    text: str


class DocumentChunkListResponse(BaseModel):
    items: list[DocumentChunkResponse]
    total: int
    limit: int
    offset: int
