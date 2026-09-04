import os
import subprocess
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]


def test_alembic_current_needs_database_configuration_only() -> None:
    environment = os.environ.copy()
    environment.update(
        {
            "AUTH_MODE": "disabled",
            "COGNITO_APP_CLIENT_ID": "",
            "COGNITO_REGION": "",
            "COGNITO_USER_POOL_ID": "",
            "DATABASE_URL": "sqlite+pysqlite:///:memory:",
            "DOCUMENT_STORAGE_BACKEND": "local",
            "ENVIRONMENT": "production",
            "FRONTEND_ORIGIN": "",
            "GEMINI_API_KEY": "",
            "INGESTION_MODE": "inline",
            "PYTHONDONTWRITEBYTECODE": "1",
            "VOYAGE_API_KEY": "",
        }
    )

    result = subprocess.run(
        [sys.executable, "-m", "alembic", "current"],
        cwd=BACKEND_DIR,
        env=environment,
        check=False,
        capture_output=True,
        text=True,
        timeout=15,
    )

    assert result.returncode == 0, result.stderr
