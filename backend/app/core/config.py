from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Know Your Lease API"
    environment: str = "development"
    debug_endpoints_enabled: bool | None = None
    database_url: str = (
        "postgresql+psycopg://lease_user:lease_password@localhost:5433/know_your_lease"
    )
    frontend_origin: str = "http://localhost:3000"
    additional_frontend_origins: str = (
        "http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001"
    )
    max_upload_size_mb: int = 20
    storage_root: Path = BACKEND_DIR / "storage"
    minimum_extractable_characters: int = 50
    chunk_target_tokens: int = 600
    chunk_max_tokens: int = 750
    chunk_overlap_tokens: int = 75
    chunk_min_tokens: int = 120
    voyage_api_key: str | None = None
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
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash"
    gemini_max_output_tokens: int = 2_048
    gemini_thinking_level: str = "low"
    gemini_max_retries: int = 1
    gemini_retry_base_seconds: float = 2.0
    answer_cache_version: str = "v1"

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @computed_field
    @property
    def max_upload_size_bytes(self) -> int:
        return self.max_upload_size_mb * 1024 * 1024

    @computed_field
    @property
    def cors_origins(self) -> list[str]:
        origins = [self.frontend_origin.rstrip("/")]
        if self.environment == "development":
            origins.extend(
                origin.strip().rstrip("/")
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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
