import uuid
from collections.abc import Sequence

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.main import app
from app.models.answer_cache import GroundedAnswerCache
from app.models.document import Document, DocumentStatus
from app.models.document_chunk import DocumentChunk
from app.services.generation import (
    GenerationConfigurationError,
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
    provider_error = GenerationProviderError(provider_detail)
    upstream_error = RuntimeError(provider_detail)
    upstream_error.status_code = 429
    provider_error.__cause__ = upstream_error
    _override_question_service(
        results=[_result(document.id)],
        generation_error=provider_error,
    )

    response = client.post(
        f"/documents/{document.id}/questions",
        json={"question": "When can the landlord enter?"},
    )

    assert response.status_code == 429
    assert response.json() == {
        "detail": {
            "code": "provider_rate_limited",
            "message": "The answer service is temporarily rate-limited. Please try again shortly.",
        }
    }
    assert provider_detail not in response.text


def test_provider_outage_is_classified_safely(
    client: TestClient,
    db_session: Session,
) -> None:
    document = _document(db_session, DocumentStatus.READY)
    provider_error = GenerationProviderError("provider payload")
    upstream_error = RuntimeError("provider payload")
    upstream_error.status_code = 503
    provider_error.__cause__ = upstream_error
    _override_question_service(results=[_result(document.id)], generation_error=provider_error)

    response = client.post(
        f"/documents/{document.id}/questions",
        json={"question": "When can the landlord enter?"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "provider_temporarily_unavailable",
            "message": "The answer service is temporarily unavailable. Please try again.",
        }
    }


def test_provider_configuration_error_is_classified_safely(
    client: TestClient,
    db_session: Session,
) -> None:
    document = _document(db_session, DocumentStatus.READY)
    _override_question_service(
        results=[_result(document.id)],
        generation_error=GenerationConfigurationError("missing secret"),
    )

    response = client.post(
        f"/documents/{document.id}/questions",
        json={"question": "When can the landlord enter?"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "provider_configuration",
            "message": "Question answering is not configured on the server.",
        }
    }


def test_invalid_provider_configuration_is_classified_safely(
    client: TestClient,
    db_session: Session,
) -> None:
    document = _document(db_session, DocumentStatus.READY)
    provider_error = GenerationProviderError("provider authentication payload")
    upstream_error = RuntimeError("provider authentication payload")
    upstream_error.status_code = 401
    provider_error.__cause__ = upstream_error
    _override_question_service(results=[_result(document.id)], generation_error=provider_error)

    response = client.post(
        f"/documents/{document.id}/questions",
        json={"question": "When can the landlord enter?"},
    )

    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "code": "provider_configuration",
            "message": "Question answering is not configured correctly on the server.",
        }
    }
    assert "authentication payload" not in response.text


def test_repeated_normalized_question_reuses_verified_document_cache(
    client: TestClient,
    db_session: Session,
) -> None:
    document = _document(db_session, DocumentStatus.READY)
    result = _result(document.id)
    db_session.add(
        DocumentChunk(
            id=result.chunk_id,
            document_id=document.id,
            chunk_index=result.chunk_index,
            page_number=result.page_number,
            text=result.text,
            token_count=result.token_count or 1,
            embedding=[0.25] * 1024,
        )
    )
    db_session.commit()
    _, embedding, retrieval, generation = _override_question_service(
        results=[result]
    )

    first = client.post(
        f"/documents/{document.id}/questions",
        json={"question": "Can I have pets?"},
    )
    second = client.post(
        f"/documents/{document.id}/questions",
        json={"question": "  CAN I   HAVE pets?  "},
    )

    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert embedding.questions == ["Can I have pets?"]
    assert len(retrieval.calls) == 1
    assert len(generation.calls) == 1
    assert db_session.query(GroundedAnswerCache).count() == 1


def test_cache_with_foreign_chunk_reference_is_not_reused(
    client: TestClient,
    db_session: Session,
) -> None:
    requested_document = _document(db_session, DocumentStatus.READY)
    other_document = _document(db_session, DocumentStatus.READY)
    foreign_result = _result(other_document.id)
    db_session.add(
        DocumentChunk(
            id=foreign_result.chunk_id,
            document_id=other_document.id,
            chunk_index=foreign_result.chunk_index,
            page_number=foreign_result.page_number,
            text=foreign_result.text,
            token_count=foreign_result.token_count or 1,
            embedding=[0.25] * 1024,
        )
    )
    db_session.add(
        GroundedAnswerCache(
            document_id=requested_document.id,
            normalized_question="can i have pets?",
            generation_version="v1",
            answer="Foreign cached answer",
            citations=[
                {
                    "chunk_id": str(foreign_result.chunk_id),
                    "page_number": 99,
                    "section_title": "Foreign",
                    "snippet": "Foreign snippet",
                    "score": 0.99,
                }
            ],
        )
    )
    db_session.commit()
    requested_result = _result(requested_document.id)
    _, embedding, _, generation = _override_question_service(results=[requested_result])

    response = client.post(
        f"/documents/{requested_document.id}/questions",
        json={"question": "Can I have pets?"},
    )

    assert response.status_code == 200
    assert response.json()["answer"] != "Foreign cached answer"
    assert embedding.questions == ["Can I have pets?"]
    assert len(generation.calls) == 1


def test_answer_cache_is_document_scoped_and_different_questions_do_not_collide(
    client: TestClient,
    db_session: Session,
) -> None:
    first_document = _document(db_session, DocumentStatus.READY)
    second_document = _document(db_session, DocumentStatus.READY)
    _, embedding, _, generation = _override_question_service(
        results=[_result(first_document.id), _result(second_document.id)]
    )

    for document_id, question in [
        (first_document.id, "Can I have pets?"),
        (first_document.id, "Can I sublet?"),
        (second_document.id, "Can I have pets?"),
    ]:
        response = client.post(f"/documents/{document_id}/questions", json={"question": question})
        assert response.status_code == 200

    assert embedding.questions == ["Can I have pets?", "Can I sublet?", "Can I have pets?"]
    assert len(generation.calls) == 3
    assert db_session.query(GroundedAnswerCache).count() == 3


def test_failed_generation_is_not_cached(
    client: TestClient,
    db_session: Session,
) -> None:
    document = _document(db_session, DocumentStatus.READY)
    _override_question_service(
        results=[_result(document.id)],
        generation_error=GenerationProviderError("failed provider"),
    )

    response = client.post(
        f"/documents/{document.id}/questions",
        json={"question": "Can I have pets?"},
    )

    assert response.status_code == 502
    assert db_session.query(GroundedAnswerCache).count() == 0


def test_source_less_abstention_is_not_cached(
    client: TestClient,
    db_session: Session,
) -> None:
    document = _document(db_session, DocumentStatus.READY)
    _, embedding, retrieval, generation = _override_question_service(
        results=[_result(document.id)],
        generation_result=GroundedGenerationResult(
            answer="I couldn't find enough information in this lease to answer that confidently.",
            source_ids=[],
        ),
    )

    for _ in range(2):
        response = client.post(
            f"/documents/{document.id}/questions",
            json={"question": "Does the building have a swimming pool?"},
        )
        assert response.status_code == 200
        assert response.json()["citations"] == []

    assert embedding.questions == [
        "Does the building have a swimming pool?",
        "Does the building have a swimming pool?",
    ]
    assert len(retrieval.calls) == 2
    assert len(generation.calls) == 2
    assert db_session.query(GroundedAnswerCache).count() == 0


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


def test_retrieve_debug_endpoint_is_hidden_when_disabled(
    client: TestClient,
    db_session: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    document = _document(db_session, DocumentStatus.READY)
    monkeypatch.setattr("app.api.routes.documents.settings.debug_endpoints_enabled", False)

    response = client.post(
        f"/documents/{document.id}/retrieve",
        json={"question": "Can I have pets?"},
    )

    assert response.status_code == 404
    assert response.json() == {"detail": "Not found."}


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
