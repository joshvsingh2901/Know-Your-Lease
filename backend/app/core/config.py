from functools import lru_cache
from pathlib import Path
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_DIR = BACKEND_DIR.parent
DEFAULT_DATABASE_URL = (
    "postgresql+psycopg://lease_user:lease_password@localhost:5433/know_your_lease"
)
DEFAULT_FRONTEND_ORIGIN = "http://localhost:3000"


class Settings(BaseSettings):
    app_name: str = "Know Your Lease API"
    environment: str = "development"
    debug_endpoints_enabled: bool | None = None
    database_url: SecretStr = SecretStr(DEFAULT_DATABASE_URL)
    frontend_origin: str = DEFAULT_FRONTEND_ORIGIN
    additional_frontend_origins: str = (
        "http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001"
    )
    max_upload_size_mb: int = Field(default=20, gt=0, le=1_024)
    storage_root: Path = BACKEND_DIR / "storage"
    minimum_extractable_characters: int = 50
    chunk_target_tokens: int = 600
    chunk_max_tokens: int = 750
    chunk_overlap_tokens: int = 75
    chunk_min_tokens: int = 120
    voyage_api_key: SecretStr | None = None
    voyage_embedding_model: str = "voyage-law-2"
    voyage_embedding_dimensions: int = 1024
    voyage_requests_per_minute: int = 3
    voyage_tokens_per_minute: int = 10_000
    voyage_batch_token_limit: int = 9_500
    voyage_batch_size: int = 128
    voyage_token_safety_factor: float = 1.1
    voyage_estimate_fallback_multiplier: float = 2.5
    voyage_max_retries: int = 2
    voyage_retry_base_seconds: float = 2.0
    gemini_api_key: SecretStr | None = None
    gemini_model: str = "gemini-3.5-flash"
    gemini_max_output_tokens: int = 2_048
    gemini_thinking_level: str = "low"
    gemini_max_retries: int = 1
    gemini_retry_base_seconds: float = 2.0
    answer_cache_version: str = Field(default="v1", min_length=1, max_length=64)

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        normalized = value.strip().casefold()
        if not normalized:
            raise ValueError("ENVIRONMENT must not be blank.")
        return normalized

    @field_validator("database_url")
    @classmethod
    def require_database_url(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().strip():
            raise ValueError("DATABASE_URL must not be blank.")
        return value

    @computed_field
    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        origins = [_validated_origin(self.frontend_origin, "FRONTEND_ORIGIN")]
        if self.environment == "development":
            origins.extend(
                _validated_origin(origin, "ADDITIONAL_FRONTEND_ORIGINS")
                for origin in self.additional_frontend_origins.split(",")
                if origin.strip()
            )
        return list(dict.fromkeys(origins))

    @computed_field
    @property
    def debug_endpoints_allowed(self) -> bool:
        if self.debug_endpoints_enabled is not None:
            return self.debug_endpoints_enabled
        return self.environment == "development"

    def database_url_value(self) -> str:
        return self.database_url.get_secret_value()


def _validated_origin(value: str, setting_name: str) -> str:
    origin = value.strip().rstrip("/")
    try:
        parsed = urlsplit(origin)
        _ = parsed.port
        valid_port = True
    except ValueError:
        valid_port = False
        parsed = urlsplit("")
    if (
        origin == "*"
        or parsed.scheme not in {"http", "https"}
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
        or not valid_port
    ):
        raise ValueError(
            f"{setting_name} must contain explicit HTTP(S) origins without paths, "
            "credentials, queries, fragments, or wildcards."
        )
    return origin


def validate_runtime_settings(config: Settings) -> None:
    problems: list[str] = []
    try:
        origins = config.cors_origins
    except ValueError as exc:
        origins = []
        problems.append(str(exc))

    frontend_public = (PROJECT_DIR / "frontend" / "public").resolve()
    storage_root = config.storage_root.resolve()
    if storage_root == frontend_public or frontend_public in storage_root.parents:
        problems.append("STORAGE_ROOT must not be inside frontend/public.")

    if config.environment == "production":
        primary_origin = origins[0] if origins else ""
        parsed_origin = urlsplit(primary_origin) if primary_origin else None
        hostname = parsed_origin.hostname if parsed_origin else None
        if hostname in {"localhost", "127.0.0.1", "::1"}:
            problems.append("Production FRONTEND_ORIGIN must not use a loopback host.")
        if parsed_origin and parsed_origin.scheme != "https":
            problems.append("Production FRONTEND_ORIGIN must use HTTPS.")
        if config.database_url_value() == DEFAULT_DATABASE_URL:
            problems.append("Production DATABASE_URL must be set explicitly.")
        if not config.voyage_api_key or not config.voyage_api_key.get_secret_value():
            problems.append("Production VOYAGE_API_KEY is required.")
        if not config.gemini_api_key or not config.gemini_api_key.get_secret_value():
            problems.append("Production GEMINI_API_KEY is required.")
        if config.debug_endpoints_allowed:
            problems.append("DEBUG_ENDPOINTS_ENABLED must be false in production.")

    if problems:
        raise RuntimeError("Invalid application configuration: " + " ".join(problems))


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
