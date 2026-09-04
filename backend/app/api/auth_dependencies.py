import logging
import uuid
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.core.auth import (
    AuthServiceUnavailableError,
    TokenVerificationError,
    verify_access_token,
)
from app.core.config import settings
from app.models.user import User

logger = logging.getLogger(__name__)

_bearer_scheme = HTTPBearer(auto_error=False)

# Fixed identity for AUTH_MODE=disabled (local development and tests). A stable id
# lets code that pre-creates documents outside a request (fixtures, scripts) assign
# ownership without depending on request/provisioning order.
LOCAL_DEV_COGNITO_SUB = "local-development-user"
LOCAL_DEV_USER_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _unauthenticated_error() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Not authenticated.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def _resolve_user(db: Session, *, cognito_sub: str, email: str | None) -> User:
    """Resolve or just-in-time provision the local user for a verified subject.

    Two simultaneous first requests from a brand-new subject can race here; the
    unique constraint on ``cognito_sub`` is the actual guard, and losing the race
    falls back to re-reading the row the other request just committed.
    """
    user = db.scalar(select(User).where(User.cognito_sub == cognito_sub))
    if user is not None:
        if email and user.email != email:
            user.email = email
            db.commit()
        return user

    user = User(cognito_sub=cognito_sub, email=email)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        user = db.scalar(select(User).where(User.cognito_sub == cognito_sub))
        if user is None:
            raise
    return user


def _resolve_local_dev_user(db: Session) -> User:
    user = db.get(User, LOCAL_DEV_USER_ID)
    if user is not None:
        return user

    user = User(id=LOCAL_DEV_USER_ID, cognito_sub=LOCAL_DEV_COGNITO_SUB, email=None)
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        user = db.get(User, LOCAL_DEV_USER_ID)
        if user is None:
            raise
    return user


def require_current_user(
    db: Annotated[Session, Depends(get_db)],
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(_bearer_scheme)],
) -> User:
    if settings.auth_mode == "disabled":
        return _resolve_local_dev_user(db)

    if credentials is None or not credentials.credentials:
        raise _unauthenticated_error()

    try:
        identity = verify_access_token(credentials.credentials)
    except TokenVerificationError:
        raise _unauthenticated_error() from None
    except AuthServiceUnavailableError as exc:
        logger.warning("Authentication service was unavailable while verifying a token.")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Authentication is temporarily unavailable. Please try again.",
        ) from exc

    return _resolve_user(db, cognito_sub=identity.subject, email=identity.email)


CurrentUser = Annotated[User, Depends(require_current_user)]
