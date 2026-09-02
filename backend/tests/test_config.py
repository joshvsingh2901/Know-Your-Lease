from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import PROJECT_DIR, Settings, validate_runtime_settings


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

    validate_runtime_settings(config)

    assert config.environment == "development"
    assert "http://localhost:3000" in config.cors_origins


def test_production_configuration_requires_explicit_safe_values(tmp_path: Path) -> None:
    config = Settings(
        _env_file=None,
        environment="production",
        frontend_origin="https://leases.example",
        additional_frontend_origins="*",
        database_url="postgresql+psycopg://user:password@db.example/leases",
        voyage_api_key="example-voyage-key",
        gemini_api_key="example-gemini-key",
        debug_endpoints_enabled=False,
        document_storage_backend="local",
        pdf_storage_dir=tmp_path / "storage",
    )

    validate_runtime_settings(config)

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
        validate_runtime_settings(config)

    message = str(exc_info.value)
    assert "Production FRONTEND_ORIGIN" in message
    assert "Production DATABASE_URL" in message
    assert "Production DOCUMENT_STORAGE_BACKEND" in message
    assert "DEBUG_ENDPOINTS_ENABLED" in message
    assert "private-voyage-key" not in message
    assert "private-gemini-key" not in message


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
        validate_runtime_settings(config)


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
        validate_runtime_settings(config)


def test_s3_storage_configuration_is_normalized_and_valid() -> None:
    config = Settings(
        _env_file=None,
        document_storage_backend=" S3 ",
        s3_bucket_name=" lease-documents ",
        aws_region=" ca-central-1 ",
    )

    validate_runtime_settings(config)

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

    validate_runtime_settings(config)
    assert config.document_storage_backend == "s3"
    assert config.s3_bucket_name == "lease-documents"
    assert config.aws_region == "ca-central-1"


def test_invalid_document_storage_backend_fails_clearly() -> None:
    with pytest.raises(ValidationError, match="document_storage_backend"):
        Settings(_env_file=None, document_storage_backend="filesystem")


@pytest.mark.parametrize("scheme", ["postgresql://", "postgres://"])
def test_railway_database_url_uses_installed_psycopg_driver(scheme: str) -> None:
    config = Settings(
        _env_file=None,
        database_url=f"{scheme}user:password@postgres.railway.internal:5432/railway",
    )

    assert config.database_url_value() == (
        "postgresql+psycopg://user:password@postgres.railway.internal:5432/railway"
    )
