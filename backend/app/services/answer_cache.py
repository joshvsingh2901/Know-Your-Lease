import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.models.answer_cache import GroundedAnswerCache
from app.models.document_chunk import DocumentChunk

_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class CachedCitation:
    chunk_id: uuid.UUID
    page_number: int
    section_title: str | None
    snippet: str
    score: float


@dataclass(frozen=True)
class CachedAnswer:
    answer: str
    citations: list[CachedCitation]


def normalize_cached_question(question: str) -> str:
    return _WHITESPACE.sub(" ", question).strip().casefold()


class AnswerCacheService:
    def __init__(self, generation_version: str) -> None:
        self.generation_version = generation_version

    def get(self, db: Session, document_id: uuid.UUID, question: str) -> CachedAnswer | None:
        normalized_question = normalize_cached_question(question)
        entry = db.scalar(
            select(GroundedAnswerCache).where(
                GroundedAnswerCache.document_id == document_id,
                GroundedAnswerCache.normalized_question == normalized_question,
                GroundedAnswerCache.generation_version == self.generation_version,
            )
        )
        if entry is None:
            return None
        try:
            citations = [
                CachedCitation(
                    chunk_id=uuid.UUID(str(item["chunk_id"])),
                    page_number=int(item["page_number"]),
                    section_title=item.get("section_title"),
                    snippet=str(item["snippet"]),
                    score=float(item["score"]),
                )
                for item in entry.citations
            ]
        except (KeyError, TypeError, ValueError):
            self._discard(db, entry)
            return None
        chunk_ids = {citation.chunk_id for citation in citations}
        owned_chunk_ids = set(
            db.scalars(
                select(DocumentChunk.id).where(
                    DocumentChunk.document_id == document_id,
                    DocumentChunk.id.in_(chunk_ids),
                )
            ).all()
        )
        if not citations or owned_chunk_ids != chunk_ids:
            self._discard(db, entry)
            return None
        return CachedAnswer(answer=entry.answer, citations=citations)

    @staticmethod
    def _discard(db: Session, entry: GroundedAnswerCache) -> None:
        db.delete(entry)
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()

    def store(
        self,
        db: Session,
        document_id: uuid.UUID,
        question: str,
        answer: str,
        citations: list[CachedCitation],
    ) -> None:
        if not citations:
            return
        normalized_question = normalize_cached_question(question)
        entry = db.scalar(
            select(GroundedAnswerCache).where(
                GroundedAnswerCache.document_id == document_id,
                GroundedAnswerCache.normalized_question == normalized_question,
                GroundedAnswerCache.generation_version == self.generation_version,
            )
        )
        citation_payload = [
            {
                "chunk_id": str(citation.chunk_id),
                "page_number": citation.page_number,
                "section_title": citation.section_title,
                "snippet": citation.snippet,
                "score": citation.score,
            }
            for citation in citations
        ]
        if entry is None:
            entry = GroundedAnswerCache(
                document_id=document_id,
                normalized_question=normalized_question,
                generation_version=self.generation_version,
                answer=answer,
                citations=citation_payload,
            )
            db.add(entry)
        else:
            entry.answer = answer
            entry.citations = citation_payload
        try:
            db.commit()
        except SQLAlchemyError:
            db.rollback()
