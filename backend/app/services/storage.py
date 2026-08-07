import logging
import os
import shutil
import uuid
from pathlib import Path
from typing import BinaryIO

from app.core.config import settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    pass


class DocumentStorage:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or settings.storage_root).resolve()
        self.uploads_root = (self.root / "uploads").resolve()

    def save(self, document_id: uuid.UUID, source: BinaryIO) -> str:
        self.uploads_root.mkdir(parents=True, exist_ok=True)
        storage_key = f"uploads/{document_id}.pdf"
        destination = self.resolve(storage_key)
        temporary = destination.with_suffix(".pdf.part")

        try:
            source.seek(0)
            with temporary.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(destination)
        except OSError as exc:
            temporary.unlink(missing_ok=True)
            raise StorageError("The uploaded PDF could not be stored.") from exc

        logger.info("Stored PDF for document %s", document_id)
        return storage_key

    def resolve(self, storage_key: str) -> Path:
        candidate = (self.root / storage_key).resolve()
        if not candidate.is_relative_to(self.uploads_root):
            raise StorageError("The document storage path is invalid.")
        return candidate

    def delete(self, storage_key: str) -> None:
        try:
            self.resolve(storage_key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("The stored PDF could not be removed.") from exc
