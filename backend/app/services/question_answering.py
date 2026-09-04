import logging
import time
import uuid
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.document import Document, DocumentStatus
from app.services.answer_cache import AnswerCacheService, CachedCitation
from app.services.citation_snippets import build_citation_snippet
from app.services.embeddings import VoyageEmbeddingService, get_embedding_service
from app.services.generation import (
    ABSTENTION_ANSWER,
    GeminiGenerationService,
    GenerationEvidence,
    GenerationResponseError,
    get_generation_service,
)
from app.services.retrieval import RetrievalResult, RetrievalService

logger = logging.getLogger(__name__)


class QuestionAnsweringError(RuntimeError):
    pass


class DocumentNotFoundError(QuestionAnsweringError):
    pass


class DocumentNotReadyError(QuestionAnsweringError):
    def __init__(self, status: DocumentStatus) -> None:
        self.status = status
        super().__init__(f"Document status is {status.value}.")


class NoRetrievedEvidenceError(QuestionAnsweringError):
    pass


@dataclass(frozen=True)
class AnswerCitation:
    chunk_id: uuid.UUID
    page_number: int
    section_title: str | None
    snippet: str
    score: float


@dataclass(frozen=True)
class QuestionAnswer:
    answer: str
    citations: list[AnswerCitation]


class QuestionAnsweringService:
    def __init__(
        self,
        *,
        embedding_service: VoyageEmbeddingService | None = None,
        retrieval_service: RetrievalService | None = None,
        generation_service: GeminiGenerationService | None = None,
        answer_cache: AnswerCacheService | None = None,
        candidate_k: int = 10,
        final_k: int = 5,
    ) -> None:
        self.embedding_service = embedding_service or get_embedding_service()
        self.retrieval_service = retrieval_service or RetrievalService()
        self.generation_service = generation_service or get_generation_service()
        self.answer_cache = answer_cache or AnswerCacheService(settings.answer_cache_version)
        self.candidate_k = candidate_k
        self.final_k = final_k

    @staticmethod
    def _require_ready(document: Document) -> None:
        if document.status != DocumentStatus.READY:
            raise DocumentNotReadyError(document.status)

    def retrieve(
        self,
        db: Session,
        document: Document,
        question: str,
    ) -> list[RetrievalResult]:
        self._require_ready(document)
        document_id = document.id
        started = time.perf_counter()
        query_embedding = self.embedding_service.embed_query(question)
        results = self.retrieval_service.search(
            db,
            document_id,
            query_embedding,
            candidate_k=self.candidate_k,
            final_k=self.final_k,
        )
        isolated_results = [
            result for result in results if result.document_id == document_id
        ]
        logger.info(
            "Retrieved %d evidence chunks for document %s in %.3f seconds",
            len(isolated_results),
            document_id,
            time.perf_counter() - started,
        )
        return isolated_results

    def answer_question(
        self,
        db: Session,
        document: Document,
        question: str,
    ) -> QuestionAnswer:
        total_started = time.perf_counter()
        self._require_ready(document)
        document_id = document.id
        cached = self.answer_cache.get(db, document_id, question)
        if cached is not None:
            logger.info("Reused grounded answer cache for document %s", document_id)
            return QuestionAnswer(
                answer=cached.answer,
                citations=[
                    AnswerCitation(
                        chunk_id=citation.chunk_id,
                        page_number=citation.page_number,
                        section_title=citation.section_title,
                        snippet=citation.snippet,
                        score=citation.score,
                    )
                    for citation in cached.citations
                ],
            )

        results = self.retrieve(db, document, question)
        if not results:
            raise NoRetrievedEvidenceError(
                "No indexed lease evidence was available for this question."
            )

        source_map = {
            f"SOURCE_{index}": result for index, result in enumerate(results, start=1)
        }
        evidence = [
            GenerationEvidence(
                source_id=source_id,
                text=result.text,
                page_number=result.page_number,
                section_title=result.section_title,
            )
            for source_id, result in source_map.items()
        ]

        generation_started = time.perf_counter()
        generated = self.generation_service.generate_answer(question, evidence)
        logger.info(
            "Generated grounded answer for document %s in %.3f seconds",
            document_id,
            time.perf_counter() - generation_started,
        )
        unknown_source_ids = set(generated.source_ids) - set(source_map)
        if unknown_source_ids:
            raise GenerationResponseError(
                "Generation returned unsupported evidence references."
            )

        citations: list[AnswerCitation] = []
        cited_source_ids: set[str] = set()
        for source_id in generated.source_ids:
            if source_id in cited_source_ids:
                continue
            cited_source_ids.add(source_id)
            result = source_map.get(source_id)
            if result is None:
                continue
            snippet = build_citation_snippet(
                question=question,
                chunk_text=result.text,
                model_quote=generated.supporting_quotes.get(source_id),
                section_title=result.section_title,
            )
            citations.append(
                AnswerCitation(
                    chunk_id=result.chunk_id,
                    page_number=result.page_number,
                    section_title=snippet.section_title,
                    snippet=snippet.text,
                    score=result.score,
                )
            )
        answer = QuestionAnswer(
            answer=generated.answer if citations else ABSTENTION_ANSWER,
            citations=citations,
        )
        self.answer_cache.store(
            db,
            document_id,
            question,
            answer.answer,
            [
                CachedCitation(
                    chunk_id=citation.chunk_id,
                    page_number=citation.page_number,
                    section_title=citation.section_title,
                    snippet=citation.snippet,
                    score=citation.score,
                )
                for citation in answer.citations
            ],
        )
        logger.info(
            "Completed question for document %s with %d citations in %.3f seconds",
            document_id,
            len(citations),
            time.perf_counter() - total_started,
        )
        return answer


@lru_cache(maxsize=1)
def get_question_answering_service() -> QuestionAnsweringService:
    return QuestionAnsweringService()
