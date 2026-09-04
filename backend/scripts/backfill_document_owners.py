"""Assign the deterministic local development user as the owner of legacy documents.

Migration 0006 adds a nullable ``documents.owner_id`` so existing pre-authentication
rows are preserved untouched: they become invisible to every user (fail-closed) until
explicitly assigned. This script is the explicit, opt-in assignment step for local
development data. It intentionally never runs automatically on deploy, so a production
database can never have its documents silently reassigned to an arbitrary user; running
it against a database with real user-owned documents is a mistake, not a workflow, and
it refuses to do so.
"""

import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.api.auth_dependencies import (
    LOCAL_DEV_COGNITO_SUB,
    LOCAL_DEV_USER_ID,
)
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.document import Document
from app.models.user import User


def main() -> int:
    if settings.environment == "production":
        print(
            "Refusing to run: ENVIRONMENT=production. This backfill assigns every "
            "ownerless document to one fixed local-development user and must never "
            "run against a database that may contain real user data.",
            file=sys.stderr,
        )
        return 1

    with SessionLocal() as db:
        user = db.get(User, LOCAL_DEV_USER_ID)
        if user is None:
            user = User(id=LOCAL_DEV_USER_ID, cognito_sub=LOCAL_DEV_COGNITO_SUB)
            db.add(user)
            try:
                db.commit()
            except IntegrityError:
                db.rollback()
                user = db.get(User, LOCAL_DEV_USER_ID)
                if user is None:
                    raise

        ownerless = db.scalars(
            select(Document).where(Document.owner_id.is_(None))
        ).all()
        for document in ownerless:
            document.owner_id = LOCAL_DEV_USER_ID
        db.commit()

    print(f"Assigned {len(ownerless)} ownerless document(s) to the local development user.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
