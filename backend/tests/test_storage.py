import io
import uuid
from pathlib import Path

import pytest

from app.services.storage import (
    InvalidStorageKeyError,
    LocalDocumentStorage,
    StorageNotFoundError,
)


def test_storage_uses_document_id_instead_of_original_filename(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path / "configured-storage")
    document_id = uuid.uuid4()

    key = storage.save(document_id, io.BytesIO(b"%PDF-safe"))

    assert key == f"uploads/{document_id}.pdf"
    assert storage.read(key) == b"%PDF-safe"
    assert storage.resolve(key) == tmp_path / "configured-storage" / key


def test_local_storage_missing_file_has_safe_error(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path / "storage")

    with pytest.raises(StorageNotFoundError, match="unavailable") as exc_info:
        storage.read(f"uploads/{uuid.uuid4()}.pdf")

    assert str(tmp_path) not in str(exc_info.value)


def test_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = LocalDocumentStorage(tmp_path / "storage")

    with pytest.raises(InvalidStorageKeyError, match="invalid"):
        storage.resolve("../outside.pdf")
