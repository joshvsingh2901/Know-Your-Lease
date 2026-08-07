from pathlib import Path

from app.services.retrieval import RetrievalResult
from scripts.evaluate_retrieval import EvaluationCase, load_cases, summarize_results


def _result(page_number: int, chunk_index: int, score: float) -> RetrievalResult:
    import uuid

    return RetrievalResult(
        chunk_id=uuid.uuid4(),
        document_id=uuid.uuid4(),
        chunk_index=chunk_index,
        page_number=page_number,
        text="source text",
        score=score,
        distance=1 - score,
    )


def test_evaluation_reports_hit_metrics_and_negative_scores() -> None:
    cases = [
        EvaluationCase("top-one", "Question one", (3,), "Rent"),
        EvaluationCase("top-three", "Question two", (8,), "Entry"),
        EvaluationCase("miss", "Question three", (13,), "Pets"),
        EvaluationCase("negative", "Unsupported", (), "Unsupported"),
    ]
    report = summarize_results(
        cases,
        {
            "top-one": [_result(3, 1, 0.9)],
            "top-three": [_result(2, 2, 0.8), _result(8, 3, 0.7)],
            "miss": [_result(5, 4, 0.6)],
            "negative": [_result(7, 5, 0.2)],
        },
    )

    assert report["metrics"] == {
        "supported_questions": 3,
        "negative_questions": 1,
        "hit_at_1": 0.3333,
        "hit_at_3": 0.6667,
        "hit_at_5": 0.6667,
        "average_first_relevant_rank": 1.5,
        "negative_top_score_average": 0.2,
    }
    assert report["cases"][1]["first_relevant_rank"] == 2
    assert report["cases"][3]["retrieved"][0]["page_number"] == 7


def test_representative_dataset_covers_supported_and_negative_questions() -> None:
    dataset = Path(__file__).resolve().parents[1] / "evaluation" / "retrieval_dataset.json"

    cases = load_cases(dataset)

    assert len(cases) == 27
    assert sum(not case.expected_pages for case in cases) == 3
    assert {case.case_id for case in cases} >= {"pets-allow", "nsf", "negative-pool"}
