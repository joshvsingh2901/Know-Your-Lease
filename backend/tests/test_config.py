from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import (
    PROJECT_DIR,
    Settings,
    validate_api_runtime_settings,
    validate_migration_runtime_settings,
    validate_worker_runtime_settings,
)


def _production_api_values() -> dict[str, object]:
    return {
        "_env_file": None,
        "environment": "production",
        "frontend_origin": "https://leases.example",
        "database_url": "postgresql+psycopg://user:password@db.example/leases",
        "document_storage_backend": "s3",
        "s3_bucket_name": "lease-documents",
        "aws_region": "ca-central-1",
        "ingestion_mode": "sqs",
        "sqs_ingestion_queue_url": (
            "https://sqs.ca-central-1.amazonaws.com/123/ingestion"
        ),
        "auth_mode": "cognito",
        "cognito_region": "ca-central-1",
        "cognito_user_pool_id": "ca-central-1_example",
        "cognito_app_client_id": "example-client-id",
        "voyage_api_key": "example-voyage-key",
        "gemini_api_key": "example-gemini-key",
        "debug_endpoints_enabled": False,
    }


def _production_worker_values() -> dict[str, object]:
    return {
        "_env_file": None,
        "environment": "production",
        "database_url": "postgresql+psycopg://worker:password@db.example/leases",
        "document_storage_backend": "s3",
        "s3_bucket_name": "lease-documents",
        "aws_region": "ca-central-1",
        "ingestion_mode": "sqs",
        "sqs_ingestion_queue_url": (
            "https://sqs.ca-central-1.amazonaws.com/123/ingestion"
        ),
        "ingestion_processing_timeout_seconds": 900,
        "voyage_api_key": "example-voyage-key",
    }


def test_secret_settings_are_masked_in_representations() -> None:
    config = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://user:private-db-password@db.example/leases",
        voyage_api_key="private-voyage-key",
        gemini_api_key="private-gemini-key",
    )

    rendered = repr(config)

    assert "private-db-password" not in rendered
    assert "private-voyage-key" not in rendered
    assert "private-gemini-key" not in rendered


def test_development_does_not_require_provider_keys(tmp_path: Path) -> None:
    config = Settings(
        _env_file=None,
        environment=" DEVELOPMENT ",
        voyage_api_key=None,
        gemini_api_key=None,
        pdf_storage_dir=tmp_path / "storage",
    )

    validate_api_runtime_settings(config)

    assert config.environment == "development"
    assert "http://localhost:3000" in config.cors_origins


def test_production_configuration_requires_explicit_safe_values() -> None:
    config = Settings(
        _env_file=None,
        environment="production",
        frontend_origin="https://leases.example",
        additional_frontend_origins="*",
        database_url="postgresql+psycopg://user:password@db.example/leases",
        voyage_api_key="example-voyage-key",
        gemini_api_key="example-gemini-key",
        debug_endpoints_enabled=False,
        ingestion_mode="sqs",
        sqs_ingestion_queue_url=(
            "https://sqs.ca-central-1.amazonaws.com/123/ingestion"
        ),
        document_storage_backend="s3",
        s3_bucket_name="lease-documents",
        aws_region="ca-central-1",
        auth_mode="cognito",
        cognito_region="ca-central-1",
        cognito_user_pool_id="ca-central-1_example",
        cognito_app_client_id="example-client-id",
    )

    validate_api_runtime_settings(config)

    assert config.cors_origins == ["https://leases.example"]


def test_unsafe_production_defaults_fail_without_echoing_secrets() -> None:
    config = Settings(
        _env_file=None,
        environment="production",
        voyage_api_key="private-voyage-key",
        gemini_api_key="private-gemini-key",
        debug_endpoints_enabled=True,
    )

    with pytest.raises(RuntimeError) as exc_info:
        validate_api_runtime_settings(config)

    message = str(exc_info.value)
    assert "Production FRONTEND_ORIGIN" in message
    assert "Production DATABASE_URL" in message
    assert "Production DOCUMENT_STORAGE_BACKEND" in message
    assert "Production INGESTION_MODE" in message
    assert "Production AUTH_MODE" in message
    assert "DEBUG_ENDPOINTS_ENABLED" in message
    assert "private-voyage-key" not in message
    assert "private-gemini-key" not in message


def test_valid_production_api_configuration_passes() -> None:
    validate_api_runtime_settings(Settings(**_production_api_values()))


def test_production_api_rejects_missing_cognito_configuration() -> None:
    values = _production_api_values()
    values["cognito_user_pool_id"] = None

    with pytest.raises(RuntimeError, match="COGNITO_USER_POOL_ID"):
        validate_api_runtime_settings(Settings(**values))


def test_production_api_rejects_missing_frontend_origin() -> None:
    values = _production_api_values()
    values.pop("frontend_origin")

    with pytest.raises(RuntimeError, match="Production FRONTEND_ORIGIN"):
        validate_api_runtime_settings(Settings(**values))


@pytest.mark.parametrize("provider_setting", ["voyage_api_key", "gemini_api_key"])
def test_production_api_rejects_missing_provider_configuration(
    provider_setting: str,
) -> None:
    values = _production_api_values()
    values[provider_setting] = None

    with pytest.raises(RuntimeError, match=provider_setting.upper()):
        validate_api_runtime_settings(Settings(**values))


def test_valid_production_worker_config_needs_no_api_only_settings() -> None:
    config = Settings(**_production_worker_values())

    validate_worker_runtime_settings(config)

    assert "frontend_origin" not in config.model_fields_set
    assert "auth_mode" not in config.model_fields_set
    assert config.gemini_api_key is None


def test_production_worker_rejects_missing_database_url() -> None:
    values = _production_worker_values()
    values.pop("database_url")

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        validate_worker_runtime_settings(Settings(**values))


@pytest.mark.parametrize("missing_setting", ["s3_bucket_name", "aws_region"])
def test_production_worker_rejects_missing_s3_configuration(
    missing_setting: str,
) -> None:
    values = _production_worker_values()
    values.pop(missing_setting)

    with pytest.raises(RuntimeError, match="S3_BUCKET_NAME and AWS_REGION"):
        validate_worker_runtime_settings(Settings(**values))


def test_production_worker_rejects_missing_sqs_configuration() -> None:
    values = _production_worker_values()
    values.pop("sqs_ingestion_queue_url")

    with pytest.raises(RuntimeError, match="SQS_INGESTION_QUEUE_URL"):
        validate_worker_runtime_settings(Settings(**values))


def test_production_worker_rejects_missing_voyage_key() -> None:
    values = _production_worker_values()
    values.pop("voyage_api_key")

    with pytest.raises(RuntimeError, match="VOYAGE_API_KEY"):
        validate_worker_runtime_settings(Settings(**values))


def test_production_migration_requires_only_database_url() -> None:
    config = Settings(
        _env_file=None,
        environment="production",
        database_url="postgresql+psycopg://migrator:password@db.example/leases",
    )

    validate_migration_runtime_settings(config)


def test_migration_rejects_implicit_default_database_url() -> None:
    config = Settings(_env_file=None)

    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        validate_migration_runtime_settings(config)


@pytest.mark.parametrize(
    "origin",
    ["*", "https://user:password@example.com", "https://example.com/private"],
)
def test_cors_rejects_non_origin_or_wildcard_values(origin: str) -> None:
    config = Settings(_env_file=None, frontend_origin=origin)

    with pytest.raises(ValueError, match=r"explicit HTTP\(S\) origins"):
        _ = config.cors_origins


def test_storage_cannot_be_configured_inside_frontend_public() -> None:
    config = Settings(
        _env_file=None,
        pdf_storage_dir=PROJECT_DIR / "frontend" / "public" / "uploads",
    )

    with pytest.raises(RuntimeError, match="PDF_STORAGE_DIR"):
        validate_api_runtime_settings(config)


def test_pdf_storage_directory_can_be_set_from_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    volume_root = tmp_path / "railway-volume"
    monkeypatch.setenv("PDF_STORAGE_DIR", str(volume_root))

    config = Settings(_env_file=None)

    assert config.pdf_storage_dir == volume_root


def test_local_document_storage_is_the_default() -> None:
    config = Settings(_env_file=None)

    assert config.document_storage_backend == "local"


def test_s3_storage_requires_bucket_and_region() -> None:
    config = Settings(_env_file=None, document_storage_backend="s3")

    with pytest.raises(RuntimeError, match="S3_BUCKET_NAME and AWS_REGION"):
        validate_api_runtime_settings(config)


def test_s3_storage_configuration_is_normalized_and_valid() -> None:
    config = Settings(
        _env_file=None,
        document_storage_backend=" S3 ",
        s3_bucket_name=" lease-documents ",
        aws_region=" ca-central-1 ",
    )

    validate_api_runtime_settings(config)

    assert config.document_storage_backend == "s3"
    assert config.s3_bucket_name == "lease-documents"
    assert config.aws_region == "ca-central-1"


def test_s3_storage_configuration_is_read_from_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("DOCUMENT_STORAGE_BACKEND", "s3")
    monkeypatch.setenv("S3_BUCKET_NAME", "lease-documents")
    monkeypatch.setenv("AWS_REGION", "ca-central-1")

    config = Settings(_env_file=None)

    validate_api_runtime_settings(config)
    assert config.document_storage_backend == "s3"
    assert config.s3_bucket_name == "lease-documents"
    assert config.aws_region == "ca-central-1"


def test_invalid_document_storage_backend_fails_clearly() -> None:
    with pytest.raises(ValidationError, match="document_storage_backend"):
        Settings(_env_file=None, document_storage_backend="filesystem")


def test_sqs_ingestion_requires_queue_url_and_region() -> None:
    config = Settings(_env_file=None, ingestion_mode="sqs")

    with pytest.raises(RuntimeError, match="SQS_INGESTION_QUEUE_URL and AWS_REGION"):
        validate_api_runtime_settings(config)


def test_sqs_ingestion_configuration_is_normalized_and_valid() -> None:
    config = Settings(
        _env_file=None,
        ingestion_mode=" SQS ",
        sqs_ingestion_queue_url=" https://sqs.ca-central-1.amazonaws.com/123/ingestion ",
        aws_region=" ca-central-1 ",
    )

    validate_api_runtime_settings(config)

    assert config.ingestion_mode == "sqs"
    assert config.sqs_ingestion_queue_url == (
        "https://sqs.ca-central-1.amazonaws.com/123/ingestion"
    )
    assert config.aws_region == "ca-central-1"


def test_invalid_ingestion_mode_fails_clearly() -> None:
    with pytest.raises(ValidationError, match="ingestion_mode"):
        Settings(_env_file=None, ingestion_mode="celery")


def test_cognito_auth_requires_region_pool_and_client() -> None:
    config = Settings(_env_file=None, auth_mode="cognito")

    with pytest.raises(
        RuntimeError,
        match="COGNITO_REGION, COGNITO_USER_POOL_ID, and COGNITO_APP_CLIENT_ID",
    ):
        validate_api_runtime_settings(config)


def test_cognito_auth_configuration_is_normalized_and_valid() -> None:
    config = Settings(
        _env_file=None,
        auth_mode=" Cognito ",
        cognito_region=" ca-central-1 ",
        cognito_user_pool_id=" ca-central-1_example ",
        cognito_app_client_id=" example-client-id ",
    )

    validate_api_runtime_settings(config)

    assert config.auth_mode == "cognito"
    assert config.cognito_region == "ca-central-1"
    assert config.cognito_user_pool_id == "ca-central-1_example"
    assert config.cognito_app_client_id == "example-client-id"
    assert config.cognito_issuer_url == (
        "https://cognito-idp.ca-central-1.amazonaws.com/ca-central-1_example"
    )
    assert config.cognito_jwks_url == (
        "https://cognito-idp.ca-central-1.amazonaws.com/ca-central-1_example"
        "/.well-known/jwks.json"
    )


def test_explicit_cognito_issuer_overrides_derived_issuer() -> None:
    config = Settings(
        _env_file=None,
        cognito_region="ca-central-1",
        cognito_user_pool_id="ca-central-1_example",
        cognito_issuer="https://issuer.example.com/custom",
    )

    assert config.cognito_issuer_url == "https://issuer.example.com/custom"
    assert config.cognito_jwks_url == (
        "https://issuer.example.com/custom/.well-known/jwks.json"
    )


def test_invalid_auth_mode_fails_clearly() -> None:
    with pytest.raises(ValidationError, match="auth_mode"):
        Settings(_env_file=None, auth_mode="basic")


def test_production_auth_mode_must_be_cognito() -> None:
    config = Settings(
        _env_file=None,
        environment="production",
        frontend_origin="https://leases.example",
        database_url="postgresql+psycopg://user:password@db.example/leases",
        voyage_api_key="example-voyage-key",
        gemini_api_key="example-gemini-key",
        debug_endpoints_enabled=False,
        ingestion_mode="sqs",
        sqs_ingestion_queue_url=(
            "https://sqs.ca-central-1.amazonaws.com/123/ingestion"
        ),
        document_storage_backend="s3",
        s3_bucket_name="lease-documents",
        aws_region="ca-central-1",
        auth_mode="disabled",
    )

    with pytest.raises(RuntimeError, match="Production AUTH_MODE must be cognito"):
        validate_api_runtime_settings(config)


@pytest.mark.parametrize("timeout", [0, 59, 43_201])
def test_ingestion_processing_timeout_is_bounded(timeout: int) -> None:
    with pytest.raises(ValidationError, match="ingestion_processing_timeout_seconds"):
        Settings(_env_file=None, ingestion_processing_timeout_seconds=timeout)


@pytest.mark.parametrize("scheme", ["postgresql://", "postgres://"])
def test_railway_database_url_uses_installed_psycopg_driver(scheme: str) -> None:
    config = Settings(
        _env_file=None,
        database_url=f"{scheme}user:password@postgres.railway.internal:5432/railway",
    )

    assert config.database_url_value() == (
        "postgresql+psycopg://user:password@postgres.railway.internal:5432/railway"
    )
