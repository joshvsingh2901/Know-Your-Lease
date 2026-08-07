from functools import lru_cache
from pathlib import Path

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    app_name: str = "Know Your Lease API"
    environment: str = "development"
    database_url: str = (
        "postgresql+psycopg://lease_user:lease_password@localhost:5433/know_your_lease"
    )
    frontend_origin: str = "http://localhost:3000"
    additional_frontend_origins: str = (
        "http://localhost:3001,http://127.0.0.1:3000,http://127.0.0.1:3001"
    )
    max_upload_size_mb: int = 20

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


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
