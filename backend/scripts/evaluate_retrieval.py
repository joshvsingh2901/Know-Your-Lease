"""Evaluate document-scoped retrieval without uploading, indexing, or generating."""

import argparse
import json
import sys
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.database import SessionLocal
from app.models.document import Document, DocumentStatus
from app.services.embeddings import get_embedding_service
from app.services.retrieval import (
    DEFAULT_CANDIDATE_K,
    DEFAULT_FINAL_K,
    RetrievalResult,
    RetrievalService,
)

DEFAULT_DATASET = BACKEND_ROOT / "evaluation" / "retrieval_dataset.json"


@dataclass(frozen=True)
class EvaluationCase:
    case_id: str
    question: str
    expected_pages: tuple[int, ...]
    expected_topic: str


def load_cases(dataset_path: Path) -> list[EvaluationCase]:
    raw_dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    raw_cases = raw_dataset.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Evaluation dataset must contain a non-empty cases list.")

    cases: list[EvaluationCase] = []
    seen_ids: set[str] = set()
    for raw_case in raw_cases:
        if not isinstance(raw_case, dict):
            raise TypeError("Each evaluation case must be an object.")
        case_id = raw_case.get("id")
        question = raw_case.get("question")
        expected_pages = raw_case.get("expected_pages")
        expected_topic = raw_case.get("expected_topic")
        if (
            not isinstance(case_id, str)
            or not case_id
            or case_id in seen_ids
            or not isinstance(question, str)
            or not question.strip()
            or not isinstance(expected_pages, list)
            or any(not isinstance(page, int) or page < 1 for page in expected_pages)
            or not isinstance(expected_topic, str)
            or not expected_topic.strip()
        ):
            raise ValueError(f"Invalid evaluation case: {case_id!r}.")
        seen_ids.add(case_id)
        cases.append(
            EvaluationCase(
                case_id=case_id,
                question=question.strip(),
                expected_pages=tuple(expected_pages),
                expected_topic=expected_topic.strip(),
            )
        )
    return cases


def _first_relevant_rank(
    results: Sequence[RetrievalResult], expected_pages: Sequence[int]
) -> int | None:
    expected = set(expected_pages)
    if not expected:
        return None
    for rank, result in enumerate(results, start=1):
        if result.page_number in expected:
            return rank
    return None


def summarize_results(
    cases: Sequence[EvaluationCase],
    results_by_case: dict[str, Sequence[RetrievalResult]],
) -> dict[str, Any]:
    supported = [case for case in cases if case.expected_pages]
    ranks: list[int] = []
    case_reports: list[dict[str, Any]] = []
    for case in cases:
        results = results_by_case[case.case_id]
        rank = _first_relevant_rank(results, case.expected_pages)
        if rank is not None:
            ranks.append(rank)
        case_reports.append(
            {
                "id": case.case_id,
                "question": case.question,
                "expected_pages": list(case.expected_pages),
                "expected_topic": case.expected_topic,
                "first_relevant_rank": rank,
                "retrieved": [
                    {
                        "rank": index,
                        "page_number": result.page_number,
                        "chunk_index": result.chunk_index,
                        "score": round(result.score, 4),
                    }
                    for index, result in enumerate(results, start=1)
                ],
            }
        )

    def hit_at(limit: int) -> float:
        if not supported:
            return 0.0
        return sum(
            1
            for report in case_reports
            if report["expected_pages"]
            and report["first_relevant_rank"] is not None
            and report["first_relevant_rank"] <= limit
        ) / len(supported)

    negative_reports = [report for report in case_reports if not report["expected_pages"]]
    negative_top_scores = [
        report["retrieved"][0]["score"]
        for report in negative_reports
        if report["retrieved"]
    ]
    return {
        "metrics": {
            "supported_questions": len(supported),
            "negative_questions": len(negative_reports),
            "hit_at_1": round(hit_at(1), 4),
            "hit_at_3": round(hit_at(3), 4),
            "hit_at_5": round(hit_at(5), 4),
            "average_first_relevant_rank": round(sum(ranks) / len(ranks), 4)
            if ranks
            else None,
            "negative_top_score_average": round(
                sum(negative_top_scores) / len(negative_top_scores), 4
            )
            if negative_top_scores
            else None,
        },
        "cases": case_reports,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluate real Voyage retrieval for an existing ready document."
    )
    parser.add_argument("document_id", type=uuid.UUID)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    cases = load_cases(args.dataset)
    with SessionLocal() as db:
        document = db.get(Document, args.document_id)
        if document is None:
            raise SystemExit("Document was not found.")
        if document.status != DocumentStatus.READY:
            raise SystemExit("Document must be ready before retrieval evaluation.")

        embeddings = get_embedding_service().embed_queries(
            [case.question for case in cases]
        )
        retrieval_service = RetrievalService()
        results_by_case = {
            case.case_id: retrieval_service.search(
                db,
                args.document_id,
                embedding,
                candidate_k=DEFAULT_CANDIDATE_K,
                final_k=DEFAULT_FINAL_K,
            )
            for case, embedding in zip(cases, embeddings, strict=True)
        }

    report = summarize_results(cases, results_by_case)
    report["document_id"] = str(args.document_id)
    report["dataset"] = str(args.dataset)
    report["candidate_k"] = DEFAULT_CANDIDATE_K
    report["final_k"] = DEFAULT_FINAL_K
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    metrics = report["metrics"]
    print(f"supported_questions={metrics['supported_questions']}")
    print(f"negative_questions={metrics['negative_questions']}")
    print(f"hit_at_1={metrics['hit_at_1']:.1%}")
    print(f"hit_at_3={metrics['hit_at_3']:.1%}")
    print(f"hit_at_5={metrics['hit_at_5']:.1%}")
    print(f"average_first_relevant_rank={metrics['average_first_relevant_rank']}")
    print(f"negative_top_score_average={metrics['negative_top_score_average']}")
    for case in report["cases"]:
        pages = [item["page_number"] for item in case["retrieved"]]
        print(f"{case['id']}: pages={pages} first_relevant_rank={case['first_relevant_rank']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
