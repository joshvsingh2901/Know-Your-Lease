import uuid
from typing import Annotated

from fastapi import Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.dependencies import get_db
from app.models.document import Document


def get_accessible_document(
    document_id: uuid.UUID,
    db: Annotated[Session, Depends(get_db)],
) -> Document:
    """Resolve one document at the route access boundary.

    The local application intentionally exposes every document. Future authentication
    should add its requester/owner predicate here so every document-scoped route inherits
    the same policy.
    """
    document = db.get(Document, document_id)
    if document is None:
        raise HTTPException(status_code=404, detail="Document not found.")
    return document


def list_accessible_documents(
    db: Annotated[Session, Depends(get_db)],
) -> list[Document]:
    """List documents visible to the current local request context."""
    return list(
        db.scalars(
            select(Document).order_by(Document.updated_at.desc(), Document.id.desc())
        ).all()
    )


AccessibleDocument = Annotated[Document, Depends(get_accessible_document)]
AccessibleDocuments = Annotated[list[Document], Depends(list_accessible_documents)]
