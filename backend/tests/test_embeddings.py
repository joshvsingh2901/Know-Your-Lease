from dataclasses import dataclass

import pytest

from app.services.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingError,
    EmbeddingProviderError,
    VoyageEmbeddingService,
)


@dataclass
class FakeEmbeddingResult:
    embeddings: list[list[float]]


class RecordingClient:
    def __init__(self, dimensions: int = 4) -> None:
        self.dimensions = dimensions
        self.calls: list[list[str]] = []
        self.input_types: list[str | None] = []

    def embed(self, texts, **kwargs):
        self.calls.append(list(texts))
        self.input_types.append(kwargs.get("input_type"))
        start = sum(len(call) for call in self.calls[:-1])
        return FakeEmbeddingResult(
            [[float(start + index)] * self.dimensions for index, _ in enumerate(texts)]
        )


class WrongCountClient:
    def embed(self, texts, **kwargs):
        return FakeEmbeddingResult([[0.0] * 4])


class TransientError(RuntimeError):
    status_code = 429

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.headers = {"retry-after": "7"}


class RetryClient(RecordingClient):
    def __init__(self) -> None:
        super().__init__()
        self.attempts = 0

    def embed(self, texts, **kwargs):
        self.attempts += 1
        if self.attempts < 3:
            raise TransientError("rate limited")
        return super().embed(texts, **kwargs)


def test_embeddings_batch_inputs_and_preserve_order() -> None:
    client = RecordingClient()
    service = VoyageEmbeddingService(
        client=client,
        dimensions=4,
        batch_size=2,
        batch_token_limit=10,
        requests_per_minute=10,
        tokens_per_minute=100,
        token_counter=lambda texts: [3 for _ in texts],
        token_safety_factor=1.0,
    )

    vectors = service.embed_documents(["a", "b", "c"], [3, 3, 3])

    assert client.calls == [["a", "b"], ["c"]]
    assert [vector[0] for vector in vectors] == [0.0, 1.0, 2.0]


def test_embeddings_validate_provider_dimensions() -> None:
    service = VoyageEmbeddingService(
        client=RecordingClient(dimensions=3),
        dimensions=4,
        requests_per_minute=10,
        tokens_per_minute=100,
    )

    with pytest.raises(EmbeddingError, match="dimensions"):
        service.embed_documents(["lease text"], [2])


def test_embeddings_validate_provider_count() -> None:
    service = VoyageEmbeddingService(
        client=WrongCountClient(),
        dimensions=4,
        requests_per_minute=10,
        tokens_per_minute=100,
    )

    with pytest.raises(EmbeddingError, match="different number"):
        service.embed_documents(["one", "two"], [1, 1])


def test_transient_retry_is_bounded_and_preserves_success() -> None:
    client = RetryClient()
    delays: list[float] = []
    service = VoyageEmbeddingService(
        client=client,
        dimensions=4,
        max_retries=2,
        retry_base_seconds=0.5,
        requests_per_minute=10,
        tokens_per_minute=100,
        token_counter=lambda texts: [1 for _ in texts],
        token_safety_factor=1.0,
        sleep=delays.append,
    )

    vectors = service.embed_documents(["lease"], [1])

    assert client.attempts == 3
    assert delays == [7.0, 7.0]
    assert len(vectors) == 1


def test_token_budget_waits_for_a_new_minute_window() -> None:
    current_time = [0.0]
    delays: list[float] = []

    def advance(seconds: float) -> None:
        delays.append(seconds)
        current_time[0] += seconds

    service = VoyageEmbeddingService(
        client=RecordingClient(),
        dimensions=4,
        batch_size=1,
        batch_token_limit=9_000,
        requests_per_minute=3,
        tokens_per_minute=10_000,
        token_counter=lambda texts: [6_000 for _ in texts],
        token_safety_factor=1.0,
        sleep=advance,
        clock=lambda: current_time[0],
    )

    service.embed_documents(["first", "second"], [6_000, 6_000])

    assert delays == [60.0]


def test_provider_token_counts_split_the_actual_failed_batch_safely() -> None:
    current_time = [0.0]
    delays: list[float] = []

    def advance(seconds: float) -> None:
        delays.append(seconds)
        current_time[0] += seconds

    client = RecordingClient()
    service = VoyageEmbeddingService(
        client=client,
        dimensions=4,
        batch_token_limit=8_000,
        requests_per_minute=3,
        tokens_per_minute=10_000,
        token_counter=lambda texts: [3_100 for _ in texts],
        token_safety_factor=1.0,
        sleep=advance,
        clock=lambda: current_time[0],
    )

    service.embed_documents(["a", "b", "c", "d"], [2_200] * 4)

    assert client.calls == [["a", "b"], ["c", "d"]]
    assert delays == [60.0]


def test_provider_failure_logs_safe_diagnostics(caplog) -> None:
    class FinalRateLimitClient:
        def embed(self, texts, **kwargs):
            error = TransientError("sensitive provider detail")
            error.http_status = 429
            error.code = "rate_limit"
            error.request_id = "request-123"
            raise error

    service = VoyageEmbeddingService(
        client=FinalRateLimitClient(),
        dimensions=4,
        max_retries=0,
        token_counter=lambda texts: [1 for _ in texts],
        token_safety_factor=1.0,
    )

    with pytest.raises(EmbeddingProviderError):
        service.embed_documents(["lease"], [1])

    assert "status=429" in caplog.text
    assert "request_id=request-123" in caplog.text
    assert "sensitive provider detail" not in caplog.text


def test_missing_key_fails_only_when_embeddings_are_requested() -> None:
    service = VoyageEmbeddingService(api_key="", dimensions=4)

    with pytest.raises(EmbeddingConfigurationError, match="VOYAGE_API_KEY"):
        service.embed_documents(["lease"], [1])


def test_embeddings_require_aligned_inputs() -> None:
    service = VoyageEmbeddingService(client=RecordingClient(), dimensions=4)

    with pytest.raises(EmbeddingError, match="aligned"):
        service.embed_documents(["one"], [])


def test_query_embedding_uses_query_input_type() -> None:
    client = RecordingClient()
    service = VoyageEmbeddingService(
        client=client,
        dimensions=4,
        token_counter=lambda texts: [4 for _ in texts],
        token_safety_factor=1.0,
        requests_per_minute=10,
        tokens_per_minute=100,
    )

    vector = service.embed_query("Can I have pets?")

    assert len(vector) == 4
    assert client.calls == [["Can I have pets?"]]
    assert client.input_types == ["query"]


def test_query_embeddings_batch_inputs_and_preserve_order() -> None:
    client = RecordingClient()
    service = VoyageEmbeddingService(
        client=client,
        dimensions=4,
        batch_size=3,
        batch_token_limit=10,
        token_counter=lambda texts: [2 for _ in texts],
        token_safety_factor=1.0,
        requests_per_minute=10,
        tokens_per_minute=100,
    )

    vectors = service.embed_queries(["pets", "fees", "entry", "sublet"])

    assert client.calls == [["pets", "fees", "entry"], ["sublet"]]
    assert client.input_types == ["query", "query"]
    assert [vector[0] for vector in vectors] == [0.0, 1.0, 2.0, 3.0]
