import io
import uuid

import boto3
import pytest
from botocore.response import StreamingBody
from botocore.stub import ANY, Stubber

from app.core.config import Settings
from app.services.storage import (
    S3DocumentStorage,
    StorageError,
    StorageNotFoundError,
    create_document_storage,
)

BUCKET = "know-your-lease-test-documents"
REGION = "ca-central-1"


@pytest.fixture()
def s3_client():
    return boto3.client(
        "s3",
        region_name=REGION,
        aws_access_key_id="test-access-key",
        aws_secret_access_key="test-secret-key",
        aws_session_token="test-session-token",
    )


def test_s3_storage_puts_and_gets_private_encrypted_pdf(s3_client) -> None:
    document_id = uuid.uuid4()
    key = f"uploads/{document_id}.pdf"
    pdf_bytes = b"%PDF-private"
    storage = S3DocumentStorage(
        bucket_name=BUCKET,
        region_name=REGION,
        client=s3_client,
    )

    with Stubber(s3_client) as stubber:
        stubber.add_response(
            "put_object",
            {"ETag": '"example"'},
            {
                "Bucket": BUCKET,
                "Key": key,
                "Body": ANY,
                "ContentType": "application/pdf",
                "ServerSideEncryption": "AES256",
            },
        )
        stubber.add_response(
            "get_object",
            {
                "Body": StreamingBody(io.BytesIO(pdf_bytes), len(pdf_bytes)),
                "ContentType": "application/pdf",
            },
            {"Bucket": BUCKET, "Key": key},
        )

        assert storage.save(document_id, io.BytesIO(pdf_bytes)) == key
        assert storage.read(key) == pdf_bytes


def test_s3_storage_maps_missing_object_to_safe_not_found(s3_client) -> None:
    key = f"uploads/{uuid.uuid4()}.pdf"
    storage = S3DocumentStorage(
        bucket_name=BUCKET,
        region_name=REGION,
        client=s3_client,
    )

    with Stubber(s3_client) as stubber:
        stubber.add_client_error(
            "get_object",
            service_error_code="NoSuchKey",
            service_message="private provider detail",
            http_status_code=404,
            expected_params={"Bucket": BUCKET, "Key": key},
        )

        with pytest.raises(StorageNotFoundError) as exc_info:
            storage.read(key)

    assert str(exc_info.value) == "The stored PDF is unavailable."
    assert BUCKET not in str(exc_info.value)
    assert "private provider detail" not in str(exc_info.value)


def test_s3_storage_maps_provider_failure_without_secret_leakage(s3_client) -> None:
    document_id = uuid.uuid4()
    key = f"uploads/{document_id}.pdf"
    storage = S3DocumentStorage(
        bucket_name=BUCKET,
        region_name=REGION,
        client=s3_client,
    )

    with Stubber(s3_client) as stubber:
        stubber.add_client_error(
            "put_object",
            service_error_code="SlowDown",
            service_message="test-secret-key and private provider detail",
            http_status_code=503,
            expected_params={
                "Bucket": BUCKET,
                "Key": key,
                "Body": ANY,
                "ContentType": "application/pdf",
                "ServerSideEncryption": "AES256",
            },
        )

        with pytest.raises(StorageError) as exc_info:
            storage.save(document_id, io.BytesIO(b"%PDF-private"))

    assert str(exc_info.value) == "The uploaded PDF could not be stored."
    assert "test-secret-key" not in str(exc_info.value)
    assert BUCKET not in str(exc_info.value)


def test_s3_storage_deletes_only_the_requested_key(s3_client) -> None:
    key = f"uploads/{uuid.uuid4()}.pdf"
    storage = S3DocumentStorage(
        bucket_name=BUCKET,
        region_name=REGION,
        client=s3_client,
    )

    with Stubber(s3_client) as stubber:
        stubber.add_response(
            "delete_object",
            {},
            {"Bucket": BUCKET, "Key": key},
        )
        storage.delete(key)


def test_storage_factory_selects_s3_without_static_credential_settings(s3_client) -> None:
    config = Settings(
        _env_file=None,
        document_storage_backend="s3",
        s3_bucket_name=BUCKET,
        aws_region=REGION,
    )

    storage = create_document_storage(config, s3_client=s3_client)

    assert isinstance(storage, S3DocumentStorage)
    assert not hasattr(config, "aws_access_key_id")
    assert not hasattr(config, "aws_secret_access_key")
