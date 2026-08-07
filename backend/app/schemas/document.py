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
