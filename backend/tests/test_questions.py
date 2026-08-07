import uuid
from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.document import Document, DocumentStatus
from app.services.generation import (
    GenerationEvidence,
    GenerationProviderError,
    GroundedGenerationResult,
)
from app.services.question_answering import (
    QuestionAnsweringService,
    get_question_answering_service,
)
from app.services.retrieval import RetrievalResult


class FakeEmbeddingService:
    def __init__(self) -> None:
        self.questions: list[str] = []

    def embed_query(self, question: str) -> list[float]:
        self.questions.append(question)
        return [0.25] * 1024


class FakeRetrievalService:
    def __init__(self, results: Sequence[RetrievalResult]) -> None:
        self.results = list(results)
        self.calls: list[tuple[uuid.UUID, int, int]] = []

    def search(
        self,
        db: Session,
        document_id: uuid.UUID,
        query_embedding: Sequence[float],
        *,
        candidate_k: int,
        final_k: int,
    ) -> list[RetrievalResult]:
        del db, query_embedding
        self.calls.append((document_id, candidate_k, final_k))
        return self.results


class FakeGenerationService:
    def __init__(
        self,
        result: GroundedGenerationResult | None = None,
        error: Exception | None = None,
    ) -> None:
        self.result = result or GroundedGenerationResult(
            answer="The lease permits pets subject to the stated conditions.",
            source_ids=["SOURCE_1"],
        )
        self.error = error
        self.calls: list[tuple[str, tuple[GenerationEvidence, ...]]] = []

    def generate_answer(
        self,
        question: str,
        evidence: Sequence[GenerationEvidence],
    ) -> GroundedGenerationResult:
        self.calls.append((question, tuple(evidence)))
        if self.error is not None:
            raise self.error
        return self.result


def _document(db: Session, status: DocumentStatus) -> Document:
    document = Document(
        id=uuid.uuid4(),
        original_filename="lease.pdf",
        status=status,
    )
    db.add(document)
    db.commit()
    return document


def _result(
    document_id: uuid.UUID,
    *,
    page_number: int = 13,
    chunk_index: int = 17,
    text: str = "The tenant may keep pets, subject to the conditions in this lease.",
    score: float = 0.91,
) -> RetrievalResult:
    return RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=document_id,
        chunk_index=chunk_index,
        page_number=page_number,
        text=text,
        score=score,
        distance=1.0 - score,
        section_title="Pets",
        paragraph_index=2,
        token_count=14,
    )


def _override_question_service(
    *,
    results: Sequence[RetrievalResult] = (),
    generation_result: GroundedGenerationResult | None = None,
    generation_error: Exception | None = None,
) -> tuple[
    QuestionAnsweringService,
    FakeEmbeddingService,
    FakeRetrievalService,
    FakeGenerationService,
]:
    embedding = FakeEmbeddingService()
    retrieval = FakeRetrievalService(results)
    generation = FakeGenerationService(generation_result, generation_error)
    service = QuestionAnsweringService(
        embedding_service=embedding,  # type: ignore[arg-type]
        retrieval_service=retrieval,  # type: ignore[arg-type]
        generation_service=generation,  # type: ignore[arg-type]
    )
    app.dependency_overrides[get_question_answering_service] = lambda: service
    return service, embedding, retrieval, generation


def test_ready_document_returns_grounded_answer_and_backend_citations(
    client: TestClient,
    db_session: Session,
) -> None:
    requested_document = _document(db_session, DocumentStatus.READY)
    other_document = _document(db_session, DocumentStatus.READY)
    requested_result = _result(requested_document.id)
    foreign_result = _result(
        other_document.id,
        page_number=99,
        text="Evidence belonging to a different document.",
    )
    _, embedding, retrieval, generation = _override_question_service(
        results=[requested_result, foreign_result],
        generation_result=GroundedGenerationResult(
            answer="Yes, this lease permits pets subject to its conditions.",
            source_ids=["SOURCE_1", "SOURCE_2", "SOURCE_1"],
            supporting_quotes={
                "SOURCE_1": "The tenant may keep pets, subject to the conditions in this lease."
            },
        ),
    )

    response = client.post(
        f"/documents/{requested_document.id}/questions",
        json={"question": "  Can I have pets?  "},
    )

    assert response.status_code == 200
    assert response.json() == {
        "answer": "Yes, this lease permits pets subject to its conditions.",
        "citations": [
            {
                "chunk_id": str(requested_result.chunk_id),
                "page_number": 13,
                "section_title": "Pets",
                "snippet": requested_result.text,
                "score": pytest.approx(0.91),
            }
        ],
    }
    assert embedding.questions == ["Can I have pets?"]
    assert retrieval.calls == [(requested_document.id, 10, 5)]
    assert len(generation.calls) == 1
    generated_question, evidence = generation.calls[0]
    assert generated_question == "Can I have pets?"
    assert [item.source_id for item in evidence] == ["SOURCE_1"]
    assert all(item.text != foreign_result.text for item in evidence)


@pytest.mark.parametrize(
    ("document_status", "expected_detail"),
    [
        (
            DocumentStatus.PROCESSING,
            "This document is still processing. Wait until it is ready.",
        ),
        (
            DocumentStatus.FAILED,
            "This document failed processing and cannot be questioned.",
        ),
    ],
)
def test_question_rejects_documents_that_are_not_ready(
    client: TestClient,
    db_session: Session,
    document_status: DocumentStatus,
    expected_detail: str,
) -> None:
    document = _document(db_session, document_status)
    _, embedding, _, generation = _override_question_service()

    response = client.post(
        f"/documents/{document.id}/questions",
        json={"question": "Can I sublet?"},
    )

    assert response.status_code == 409
    assert response.json() == {"detail": expected_detail}
    assert embedding.questions == []
    assert generation.calls == []


def test_question_for_nonexistent_document_returns_not_found(
    client: TestClient,
) -> None:
    _override_question_service()

    response = client.post(
        f"/documents/{uuid.uuid4()}/questions",
        json={"question": "Can I sublet?"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Document not found."}


@pytest.mark.parametrize("question", ["", "   \n\t  "])
def test_blank_question_is_rejected_before_orchestration(
    client: TestClient,
    question: str,
) -> None:
    _, embedding, retrieval, generation = _override_question_service()

    response = client.post(
        f"/documents/{uuid.uuid4()}/questions",
        json={"question": question},
    )

    assert response.status_code == 422
    assert embedding.questions == []
    assert retrieval.calls == []
    assert generation.calls == []


def test_generation_provider_failure_returns_only_safe_api_error(
    client: TestClient,
    db_session: Session,
) -> None:
    document = _document(db_session, DocumentStatus.READY)
    provider_detail = "internal provider request abc-123 failed"
    _override_question_service(
        results=[_result(document.id)],
        generation_error=GenerationProviderError(provider_detail),
    )

    response = client.post(
        f"/documents/{document.id}/questions",
        json={"question": "When can the landlord enter?"},
    )

    assert response.status_code == 502
    assert response.json() == {
        "detail": "The question service could not complete this request. Please try again."
    }
    assert provider_detail not in response.text


def test_retrieve_endpoint_returns_document_scoped_evidence_without_embeddings(
    client: TestClient,
    db_session: Session,
) -> None:
    requested_document = _document(db_session, DocumentStatus.READY)
    other_document = _document(db_session, DocumentStatus.READY)
    requested_result = _result(requested_document.id, page_number=8, chunk_index=4)
    foreign_result = _result(other_document.id, page_number=42, chunk_index=1)
    _, embedding, _, generation = _override_question_service(
        results=[foreign_result, requested_result]
    )

    response = client.post(
        f"/documents/{requested_document.id}/retrieve",
        json={"question": "What extra fees should I know about?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "results": [
            {
                "chunk_id": str(requested_result.chunk_id),
                "chunk_index": 4,
                "page_number": 8,
                "section_title": "Pets",
                "text": requested_result.text,
                "score": pytest.approx(0.91),
            }
        ]
    }
    assert embedding.questions == ["What extra fees should I know about?"]
    assert generation.calls == []
    assert "embedding" not in response.text
    assert str(foreign_result.chunk_id) not in response.text


def test_ready_document_with_no_chunks_fails_safely(
    client: TestClient,
    db_session: Session,
) -> None:
    document = _document(db_session, DocumentStatus.READY)
    _override_question_service(results=[])

    answer_response = client.post(
        f"/documents/{document.id}/questions",
        json={"question": "What happens if I end the lease early?"},
    )
    retrieval_response = client.post(
        f"/documents/{document.id}/retrieve",
        json={"question": "What happens if I end the lease early?"},
    )

    assert answer_response.status_code == 409
    assert answer_response.json() == {
        "detail": "This document has no indexed evidence available."
    }
    assert retrieval_response.status_code == 200
    assert retrieval_response.json() == {"results": []}


def test_malformed_document_id_is_rejected(client: TestClient) -> None:
    _override_question_service()

    response = client.post(
        "/documents/not-a-uuid/questions",
        json={"question": "Can I have pets?"},
    )

    assert response.status_code == 422
