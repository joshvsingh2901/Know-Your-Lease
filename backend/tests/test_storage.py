import io
import uuid
from pathlib import Path

import pytest

from app.services.storage import DocumentStorage, StorageError


def test_storage_uses_document_id_instead_of_original_filename(tmp_path: Path) -> None:
    storage = DocumentStorage(tmp_path / "storage")
    document_id = uuid.uuid4()

    key = storage.save(document_id, io.BytesIO(b"%PDF-safe"))

    assert key == f"uploads/{document_id}.pdf"
    assert storage.resolve(key).read_bytes() == b"%PDF-safe"


def test_storage_rejects_path_traversal(tmp_path: Path) -> None:
    storage = DocumentStorage(tmp_path / "storage")

    with pytest.raises(StorageError, match="invalid"):
        storage.resolve("../outside.pdf")
