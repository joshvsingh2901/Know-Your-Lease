import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth_dependencies import CurrentUser
from app.api.dependencies import get_db
from app.models.document import Document


def get_accessible_document(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
) -> Document:
    """Resolve one document at the route access boundary.

    Every document-scoped route depends on this function (or
    :func:`list_accessible_documents`) rather than querying ``Document`` directly, so the
    ownership predicate lives in exactly one place. A document that does not exist and a
    document owned by someone else are made indistinguishable on purpose: both return 404,
    never 403, so a document UUID cannot be used to probe for another user's document.
    A document with no owner (``owner_id IS NULL``, e.g. a pre-authentication legacy row)
    matches no user and is therefore inaccessible to everyone until explicitly assigned.
    """
    document = db.scalar(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == current_user.id,
        )
    )
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


def list_accessible_documents(
    db: Annotated[Session, Depends(get_db)],
    current_user: CurrentUser,
) -> list[Document]:
    """List documents owned by the current authenticated user."""
    return list(
        db.scalars(
            select(Document)
            .where(Document.owner_id == current_user.id)
            .order_by(Document.updated_at.desc(), Document.id.desc())
        ).all()
    )


AccessibleDocument = Annotated[Document, Depends(get_accessible_document)]
AccessibleDocuments = Annotated[list[Document], Depends(list_accessible_documents)]
