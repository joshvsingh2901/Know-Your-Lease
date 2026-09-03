import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import CheckConstraint, DateTime, Enum, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.answer_cache import GroundedAnswerCache
    from app.models.document_chunk import DocumentChunk


class DocumentStatus(str, enum.Enum):
    UPLOADED = "uploaded"
    QUEUED = "queued"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        CheckConstraint(
            "current_ingestion_version > 0",
            name="ck_documents_current_ingestion_version_positive",
        ),
        CheckConstraint(
            "completed_ingestion_version IS NULL OR completed_ingestion_version > 0",
            name="ck_documents_completed_ingestion_version_positive",
        ),
        CheckConstraint(
            "ingestion_attempts >= 0",
            name="ck_documents_ingestion_attempts_nonnegative",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    current_ingestion_version: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=1,
        server_default="1",
    )
    completed_ingestion_version: Mapped[int | None] = mapped_column(
        Integer,
        nullable=True,
    )
    ingestion_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    last_ingestion_error_code: Mapped[str | None] = mapped_column(
        String(64),
        nullable=True,
    )
    last_ingestion_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_ingestion_failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    status: Mapped[DocumentStatus] = mapped_column(
        Enum(
            DocumentStatus,
            name="document_status",
            values_callable=lambda items: [item.value for item in items],
        ),
        nullable=False,
        default=DocumentStatus.UPLOADED,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
    answer_cache_entries: Mapped[list["GroundedAnswerCache"]] = relationship(
        back_populates="document", cascade="all, delete-orphan"
    )
