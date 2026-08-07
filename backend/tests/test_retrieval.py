import uuid
from collections.abc import Sequence

import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.orm import Session

from app.services.retrieval import (
    RetrievalResult,
    RetrievalService,
    _candidate_statement,
)


def result(
    *,
    document_id: uuid.UUID,
    chunk_index: int,
    distance: float,
    text: str,
    page_number: int = 1,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        chunk_index=chunk_index,
        page_number=page_number,
        text=text,
        score=1.0 - distance,
        distance=distance,
        token_count=20,
    )


class RecordingLoader:
    def __init__(self, candidates: Sequence[RetrievalResult]) -> None:
        self.candidates = candidates
        self.calls: list[tuple[uuid.UUID, int, int]] = []

    def __call__(
        self,
        db: Session,
        document_id: uuid.UUID,
        query_embedding: Sequence[float],
        candidate_k: int,
    ) -> Sequence[RetrievalResult]:
        self.calls.append((document_id, len(query_embedding), candidate_k))
        return self.candidates


def test_pgvector_query_filters_document_before_cosine_ordering() -> None:
    document_id = uuid.uuid4()
    statement = _candidate_statement(document_id, [0.0] * 1024, 10)
    compiled = statement.compile(dialect=postgresql.dialect())
    sql = str(compiled)

    assert "document_chunks.embedding <=>" in sql
    assert "WHERE document_chunks.document_id =" in sql
    assert "ORDER BY distance ASC" in sql
    assert sql.index("WHERE document_chunks.document_id") < sql.index("ORDER BY")
    assert document_id in compiled.params.values()
    assert 10 in compiled.params.values()


def test_retrieval_is_scoped_ordered_and_respects_requested_top_k() -> None:
    document_id = uuid.uuid4()
    other_document_id = uuid.uuid4()
    expected_first = result(
        document_id=document_id,
        chunk_index=3,
        distance=0.08,
        text="The tenant may keep one cat with the landlord's written consent.",
    )
    expected_second = result(
        document_id=document_id,
        chunk_index=8,
        distance=0.15,
        text="A refundable pet deposit is due before the animal moves in.",
        page_number=3,
    )
    loader = RecordingLoader(
        [
            expected_second,
            result(
                document_id=other_document_id,
                chunk_index=1,
                distance=0.01,
                text="A different lease allows all pets.",
            ),
            expected_first,
        ]
    )
    service = RetrievalService(
        candidate_loader=loader,
        embedding_dimensions=4,
    )

    retrieved = service.search(
        object(),  # type: ignore[arg-type]
        document_id,
        [0.0] * 4,
        candidate_k=7,
        final_k=2,
    )

    assert retrieved == [expected_first, expected_second]
    assert loader.calls == [(document_id, 4, 7)]
    assert all(item.document_id == document_id for item in retrieved)
    assert all(not hasattr(item, "embedding") for item in retrieved)


def test_retrieval_diversifies_near_duplicates_but_keeps_distinct_neighbors() -> None:
    document_id = uuid.uuid4()
    base_text = (
        "The tenant must obtain written consent before keeping a pet in the unit. "
        "The tenant remains responsible for damage caused by the pet. "
    ) * 4
    first = result(
        document_id=document_id,
        chunk_index=4,
        distance=0.05,
        text=base_text,
        page_number=6,
    )
    duplicate = result(
        document_id=document_id,
        chunk_index=5,
        distance=0.06,
        text=base_text + "Administrative wording.",
        page_number=6,
    )
    distinct_neighbor = result(
        document_id=document_id,
        chunk_index=3,
        distance=0.07,
        text=(
            "The landlord may enter after giving the notice required by this agreement. "
            "Emergency entry does not require advance notice."
        ),
        page_number=6,
    )
    loader = RecordingLoader([duplicate, distinct_neighbor, first])
    service = RetrievalService(
        candidate_loader=loader,
        embedding_dimensions=4,
    )

    retrieved = service.search(
        object(),  # type: ignore[arg-type]
        document_id,
        [0.0] * 4,
        final_k=3,
    )

    assert retrieved == [first, distinct_neighbor]


def test_retrieval_returns_empty_when_no_chunks_match() -> None:
    service = RetrievalService(
        candidate_loader=RecordingLoader([]),
        embedding_dimensions=4,
    )

    assert (
        service.search(
            object(),  # type: ignore[arg-type]
            uuid.uuid4(),
            [0.0] * 4,
        )
        == []
    )


@pytest.mark.parametrize(
    ("candidate_k", "final_k"),
    [(0, 1), (5, 0), (3, 4)],
)
def test_retrieval_rejects_invalid_limits(candidate_k: int, final_k: int) -> None:
    with pytest.raises(ValueError, match="Retrieval limits|final_k"):
        RetrievalService().search(
            object(),  # type: ignore[arg-type]
            uuid.uuid4(),
            [0.0] * 1024,
            candidate_k=candidate_k,
            final_k=final_k,
        )


def test_retrieval_rejects_invalid_query_vectors() -> None:
    service = RetrievalService(
        candidate_loader=RecordingLoader([]),
        embedding_dimensions=4,
    )

    with pytest.raises(ValueError, match="dimensions"):
        service.search(
            object(),  # type: ignore[arg-type]
            uuid.uuid4(),
            [0.0] * 3,
        )
    with pytest.raises(ValueError, match="non-finite"):
        service.search(
            object(),  # type: ignore[arg-type]
            uuid.uuid4(),
            [0.0, 0.0, 0.0, float("nan")],
        )
