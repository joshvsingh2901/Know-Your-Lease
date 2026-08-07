import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(DocumentStatus, name="document_status", values_callable=lambda items: [item.value for item in items]),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
