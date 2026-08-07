from pathlib import Path

import pytest

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
        storage_root=tmp_path / "storage",
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
        storage_root=tmp_path / "storage",
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
        storage_root=PROJECT_DIR / "frontend" / "public" / "uploads",
    )

    with pytest.raises(RuntimeError, match="STORAGE_ROOT"):
        validate_runtime_settings(config)
