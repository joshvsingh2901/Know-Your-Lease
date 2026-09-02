import logging
import os
import shutil
import uuid
from abc import ABC, abstractmethod
from contextlib import suppress
from functools import lru_cache
from pathlib import Path, PurePosixPath
from typing import BinaryIO

import boto3
from botocore.client import BaseClient
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import Settings, settings

logger = logging.getLogger(__name__)


class StorageError(RuntimeError):
    pass


class StorageNotFoundError(StorageError):
    pass


class InvalidStorageKeyError(StorageError):
    pass


class DocumentStorage(ABC):
    @abstractmethod
    def save(self, document_id: uuid.UUID, source: BinaryIO) -> str:
        """Persist a PDF and return its opaque storage key."""

    @abstractmethod
    def read(self, storage_key: str) -> bytes:
        """Return PDF bytes for a storage key."""

    @abstractmethod
    def delete(self, storage_key: str) -> None:
        """Delete a PDF when upload rollback requires cleanup."""


class LocalDocumentStorage(DocumentStorage):
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or settings.pdf_storage_dir).resolve()
        self.uploads_root = (self.root / "uploads").resolve()

    def save(self, document_id: uuid.UUID, source: BinaryIO) -> str:
        self.uploads_root.mkdir(parents=True, exist_ok=True)
        storage_key = _storage_key(document_id)
        destination = self.resolve(storage_key)
        temporary = destination.with_suffix(".pdf.part")

        try:
            source.seek(0)
            with temporary.open("wb") as output:
                shutil.copyfileobj(source, output, length=1024 * 1024)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(destination)
        except (OSError, ValueError) as exc:
            with suppress(OSError):
                temporary.unlink(missing_ok=True)
            raise StorageError("The uploaded PDF could not be stored.") from exc

        logger.info("Stored PDF for document %s in local storage", document_id)
        return storage_key

    def read(self, storage_key: str) -> bytes:
        try:
            return self.resolve(storage_key).read_bytes()
        except FileNotFoundError as exc:
            raise StorageNotFoundError("The stored PDF is unavailable.") from exc
        except OSError as exc:
            raise StorageError("The stored PDF could not be read.") from exc

    def resolve(self, storage_key: str) -> Path:
        _validate_storage_key(storage_key)
        candidate = (self.root / storage_key).resolve()
        if not candidate.is_relative_to(self.uploads_root):
            raise InvalidStorageKeyError("The document storage key is invalid.")
        return candidate

    def delete(self, storage_key: str) -> None:
        try:
            self.resolve(storage_key).unlink(missing_ok=True)
        except OSError as exc:
            raise StorageError("The stored PDF could not be removed.") from exc


class S3DocumentStorage(DocumentStorage):
    def __init__(
        self,
        *,
        bucket_name: str,
        region_name: str,
        client: BaseClient | None = None,
    ) -> None:
        self.bucket_name = bucket_name
        self.region_name = region_name
        self.client = client or boto3.client("s3", region_name=region_name)

    def save(self, document_id: uuid.UUID, source: BinaryIO) -> str:
        storage_key = _storage_key(document_id)
        try:
            source.seek(0)
            self.client.put_object(
                Bucket=self.bucket_name,
                Key=storage_key,
                Body=source,
                ContentType="application/pdf",
                ServerSideEncryption="AES256",
            )
        except (BotoCoreError, ClientError, OSError, ValueError) as exc:
            raise StorageError("The uploaded PDF could not be stored.") from exc

        logger.info("Stored PDF for document %s in S3", document_id)
        return storage_key

    def read(self, storage_key: str) -> bytes:
        _validate_storage_key(storage_key)
        body = None
        try:
            response = self.client.get_object(Bucket=self.bucket_name, Key=storage_key)
            body = response["Body"]
            return body.read()
        except ClientError as exc:
            if _is_missing_object(exc):
                raise StorageNotFoundError("The stored PDF is unavailable.") from exc
            raise StorageError("The stored PDF could not be read.") from exc
        except (BotoCoreError, KeyError, OSError) as exc:
            raise StorageError("The stored PDF could not be read.") from exc
        finally:
            if body is not None:
                with suppress(Exception):
                    body.close()

    def delete(self, storage_key: str) -> None:
        _validate_storage_key(storage_key)
        try:
            self.client.delete_object(Bucket=self.bucket_name, Key=storage_key)
        except (BotoCoreError, ClientError) as exc:
            raise StorageError("The stored PDF could not be removed.") from exc


def _storage_key(document_id: uuid.UUID) -> str:
    return f"uploads/{document_id}.pdf"


def _validate_storage_key(storage_key: str) -> None:
    path = PurePosixPath(storage_key)
    if (
        str(path) != storage_key
        or path.parent != PurePosixPath("uploads")
        or path.suffix != ".pdf"
    ):
        raise InvalidStorageKeyError("The document storage key is invalid.")
    try:
        parsed_id = uuid.UUID(path.stem)
    except ValueError as exc:
        raise InvalidStorageKeyError("The document storage key is invalid.") from exc
    if str(parsed_id) != path.stem:
        raise InvalidStorageKeyError("The document storage key is invalid.")


def _is_missing_object(exc: ClientError) -> bool:
    code = str(exc.response.get("Error", {}).get("Code", ""))
    status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode")
    return code in {"NoSuchKey", "NotFound", "404"} or status == 404


def create_document_storage(
    config: Settings,
    *,
    s3_client: BaseClient | None = None,
) -> DocumentStorage:
    if config.document_storage_backend == "local":
        return LocalDocumentStorage(config.pdf_storage_dir)
    if config.document_storage_backend == "s3":
        if not config.s3_bucket_name or not config.aws_region:
            raise RuntimeError("S3 document storage configuration is incomplete.")
        return S3DocumentStorage(
            bucket_name=config.s3_bucket_name,
            region_name=config.aws_region,
            client=s3_client,
        )
    raise RuntimeError("DOCUMENT_STORAGE_BACKEND must be 'local' or 's3'.")


@lru_cache(maxsize=1)
def get_document_storage() -> DocumentStorage:
    return create_document_storage(settings)
