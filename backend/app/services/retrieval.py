import math
import re
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document_chunk import DocumentChunk

DEFAULT_CANDIDATE_K = 10
DEFAULT_FINAL_K = 5
_NEAR_DUPLICATE_THRESHOLD = 0.92
_ADJACENT_DUPLICATE_THRESHOLD = 0.78
_SHINGLE_SIZE = 5
_WORD_PATTERN = re.compile(r"\w+")


@dataclass(frozen=True)
class RetrievalResult:
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    chunk_index: int
    page_number: int
    text: str
    score: float
    distance: float
    section_title: str | None = None
    paragraph_index: int | None = None
    token_count: int | None = None


CandidateLoader = Callable[
    [Session, uuid.UUID, Sequence[float], int],
    Sequence[RetrievalResult],
]


def _candidate_statement(
    document_id: uuid.UUID,
    query_embedding: Sequence[float],
    candidate_k: int,
) -> Select:
    """Build the exact, document-scoped pgvector cosine query."""
    distance = DocumentChunk.embedding.cosine_distance(list(query_embedding)).label(
        "distance"
    )
    return (
        select(
            DocumentChunk.id.label("chunk_id"),
            DocumentChunk.document_id,
            DocumentChunk.chunk_index,
            DocumentChunk.page_number,
            DocumentChunk.text,
            DocumentChunk.section_title,
            DocumentChunk.paragraph_index,
            DocumentChunk.token_count,
            distance,
        )
        .where(DocumentChunk.document_id == document_id)
        .order_by(distance.asc(), DocumentChunk.chunk_index.asc())
        .limit(candidate_k)
    )


def _load_pgvector_candidates(
    db: Session,
    document_id: uuid.UUID,
    query_embedding: Sequence[float],
    candidate_k: int,
) -> list[RetrievalResult]:
    rows = db.execute(
        _candidate_statement(document_id, query_embedding, candidate_k)
    ).mappings()
    candidates: list[RetrievalResult] = []
    for row in rows:
        distance = float(row["distance"])
        candidates.append(
            RetrievalResult(
                chunk_id=row["chunk_id"],
                document_id=row["document_id"],
                chunk_index=row["chunk_index"],
                page_number=row["page_number"],
                text=row["text"],
                score=1.0 - distance,
                distance=distance,
                section_title=row["section_title"],
                paragraph_index=row["paragraph_index"],
                token_count=row["token_count"],
            )
        )
    return candidates


def _text_shingles(text: str) -> frozenset[tuple[str, ...]]:
    words = _WORD_PATTERN.findall(text.casefold())
    if len(words) < _SHINGLE_SIZE:
        return frozenset((word,) for word in words)
    return frozenset(
        tuple(words[index : index + _SHINGLE_SIZE])
        for index in range(len(words) - _SHINGLE_SIZE + 1)
    )


def _overlap_ratio(left: str, right: str) -> float:
    left_shingles = _text_shingles(left)
    right_shingles = _text_shingles(right)
    if not left_shingles or not right_shingles:
        return 0.0
    return len(left_shingles & right_shingles) / min(
        len(left_shingles), len(right_shingles)
    )


def _is_near_duplicate(candidate: RetrievalResult, selected: RetrievalResult) -> bool:
    adjacent = (
        candidate.page_number == selected.page_number
        and abs(candidate.chunk_index - selected.chunk_index) == 1
    )
    threshold = (
        _ADJACENT_DUPLICATE_THRESHOLD if adjacent else _NEAR_DUPLICATE_THRESHOLD
    )
    return _overlap_ratio(candidate.text, selected.text) >= threshold


class RetrievalService:
    def __init__(
        self,
        *,
        embedding_dimensions: int | None = None,
        candidate_loader: CandidateLoader = _load_pgvector_candidates,
    ) -> None:
        self.embedding_dimensions = (
            embedding_dimensions or settings.voyage_embedding_dimensions
        )
        self.candidate_loader = candidate_loader

    @staticmethod
    def _validate_limits(candidate_k: int, final_k: int) -> None:
        if candidate_k <= 0 or final_k <= 0:
            raise ValueError("Retrieval limits must be positive.")
        if final_k > candidate_k:
            raise ValueError("final_k cannot exceed candidate_k.")

    def search(
        self,
        db: Session,
        document_id: uuid.UUID,
        query_embedding: Sequence[float],
        candidate_k: int = DEFAULT_CANDIDATE_K,
        final_k: int = DEFAULT_FINAL_K,
    ) -> list[RetrievalResult]:
        self._validate_limits(candidate_k, final_k)
        if len(query_embedding) != self.embedding_dimensions:
            raise ValueError(
                "Query embedding dimensions do not match the stored document vectors."
            )
        if any(not math.isfinite(float(value)) for value in query_embedding):
            raise ValueError("Query embedding contains a non-finite value.")

        loaded = self.candidate_loader(
            db,
            document_id,
            query_embedding,
            candidate_k,
        )
        candidates = sorted(
            (
                candidate
                for candidate in loaded
                if candidate.document_id == document_id
            ),
            key=lambda candidate: (candidate.distance, candidate.chunk_index),
        )[:candidate_k]

        selected: list[RetrievalResult] = []
        for candidate in candidates:
            if any(
                _is_near_duplicate(candidate, existing) for existing in selected
            ):
                continue
            selected.append(candidate)
            if len(selected) == final_k:
                break
        return selected


@lru_cache(maxsize=1)
def get_retrieval_service() -> RetrievalService:
    return RetrievalService()
