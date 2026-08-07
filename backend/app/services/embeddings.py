import logging
import math
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from functools import lru_cache
from typing import Any

import voyageai

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmbeddingError(RuntimeError):
    pass


class EmbeddingConfigurationError(EmbeddingError):
    pass


class EmbeddingProviderError(EmbeddingError):
    pass


@dataclass(frozen=True)
class _EmbeddingBatch:
    texts: list[str]
    token_count: int


@dataclass(frozen=True)
class _RequestUsage:
    timestamp: float
    token_count: int


class VoyageEmbeddingService:
    def __init__(
        self,
        *,
        client: Any | None = None,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
        requests_per_minute: int | None = None,
        tokens_per_minute: int | None = None,
        batch_token_limit: int | None = None,
        batch_size: int | None = None,
        max_retries: int | None = None,
        retry_base_seconds: float | None = None,
        token_safety_factor: float | None = None,
        estimate_fallback_multiplier: float | None = None,
        token_counter: Callable[[list[str]], list[int]] | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client = client
        self.api_key = api_key if api_key is not None else settings.voyage_api_key
        self.model = model or settings.voyage_embedding_model
        self.dimensions = dimensions or settings.voyage_embedding_dimensions
        self.requests_per_minute = requests_per_minute or settings.voyage_requests_per_minute
        self.tokens_per_minute = tokens_per_minute or settings.voyage_tokens_per_minute
        self.batch_token_limit = batch_token_limit or settings.voyage_batch_token_limit
        self.batch_size = batch_size or settings.voyage_batch_size
        self.max_retries = settings.voyage_max_retries if max_retries is None else max_retries
        self.retry_base_seconds = retry_base_seconds or settings.voyage_retry_base_seconds
        self.token_safety_factor = (
            token_safety_factor or settings.voyage_token_safety_factor
        )
        self.estimate_fallback_multiplier = (
            estimate_fallback_multiplier or settings.voyage_estimate_fallback_multiplier
        )
        self.token_counter = token_counter
        self.sleep = sleep
        self.clock = clock
        self._request_lock = threading.Lock()
        self._request_history: deque[_RequestUsage] = deque()

    def _get_client(self) -> Any:
        if self.client is not None:
            return self.client
        if not self.api_key:
            raise EmbeddingConfigurationError(
                "Document indexing is not configured because VOYAGE_API_KEY is missing."
            )
        self.client = voyageai.Client(api_key=self.api_key, max_retries=0, timeout=60)
        return self.client

    def _budget_token_counts(
        self,
        texts: list[str],
        estimated_token_counts: list[int],
    ) -> list[int]:
        if self.token_counter is not None:
            provider_counts = self.token_counter(texts)
        else:
            client = self._get_client()
            try:
                encodings = client.tokenize(texts, model=self.model)
                provider_counts = [len(encoding) for encoding in encodings]
            except Exception as exc:  # noqa: BLE001 - safe conservative fallback boundary
                logger.warning(
                    "Voyage tokenizer unavailable (%s); using conservative estimates",
                    type(exc).__name__,
                )
                return [
                    max(1, math.ceil(count * self.estimate_fallback_multiplier))
                    for count in estimated_token_counts
                ]

        if len(provider_counts) != len(texts) or any(count <= 0 for count in provider_counts):
            raise EmbeddingError("Voyage token counts were invalid or misaligned.")
        return [
            max(1, math.ceil(count * self.token_safety_factor))
            for count in provider_counts
        ]

    def _make_batches(self, texts: list[str], token_counts: list[int]) -> list[_EmbeddingBatch]:
        batches: list[_EmbeddingBatch] = []
        batch_texts: list[str] = []
        batch_tokens = 0
        for text, token_count in zip(texts, token_counts, strict=True):
            if token_count > self.batch_token_limit:
                raise EmbeddingError("A chunk exceeds the configured embedding batch token limit.")
            if batch_texts and (
                len(batch_texts) >= self.batch_size
                or batch_tokens + token_count > self.batch_token_limit
            ):
                batches.append(_EmbeddingBatch(batch_texts, batch_tokens))
                batch_texts = []
                batch_tokens = 0
            batch_texts.append(text)
            batch_tokens += token_count
        if batch_texts:
            batches.append(_EmbeddingBatch(batch_texts, batch_tokens))
        return batches

    @staticmethod
    def _is_transient(exc: Exception) -> bool:
        status_code = (
            getattr(exc, "http_status", None)
            or getattr(exc, "status_code", None)
            or getattr(exc, "status", None)
        )
        if status_code in {429, 500, 502, 503, 504}:
            return True
        name = type(exc).__name__.lower()
        return any(marker in name for marker in ("ratelimit", "timeout", "unavailable"))

    @staticmethod
    def _provider_error_fields(exc: Exception) -> tuple[object, object, object, object]:
        status_code = (
            getattr(exc, "http_status", None)
            or getattr(exc, "status_code", None)
            or getattr(exc, "status", None)
        )
        return (
            status_code,
            getattr(exc, "code", None),
            getattr(exc, "request_id", None),
            type(exc).__name__,
        )

    @staticmethod
    def _retry_after_seconds(exc: Exception) -> float | None:
        headers = getattr(exc, "headers", None)
        if not isinstance(headers, dict):
            return None
        normalized = {str(key).lower(): value for key, value in headers.items()}
        milliseconds = normalized.get("retry-after-ms")
        if milliseconds is not None:
            try:
                return max(0.0, float(milliseconds) / 1000)
            except (TypeError, ValueError):
                return None
        value = normalized.get("retry-after")
        if value is None:
            return None
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            try:
                retry_at = parsedate_to_datetime(str(value))
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                return max(0.0, (retry_at - datetime.now(UTC)).total_seconds())
            except (TypeError, ValueError, OverflowError):
                return None

    def _embed_batch(
        self,
        batch: _EmbeddingBatch,
        *,
        input_type: str,
    ) -> list[list[float]]:
        client = self._get_client()
        for attempt in range(self.max_retries + 1):
            self._reserve_provider_request(batch.token_count)
            try:
                request_started = self.clock()
                result = client.embed(
                    batch.texts,
                    model=self.model,
                    input_type=input_type,
                    truncation=False,
                )
                provider_tokens = getattr(result, "total_tokens", None)
                logger.info(
                    "Voyage embedding batch succeeded (%d chunks, provider_tokens=%s, "
                    "request_seconds=%.3f)",
                    len(batch.texts),
                    provider_tokens if provider_tokens is not None else "unavailable",
                    max(0.0, self.clock() - request_started),
                )
                return [list(vector) for vector in result.embeddings]
            except Exception as exc:
                if attempt >= self.max_retries or not self._is_transient(exc):
                    status_code, code, request_id, error_type = self._provider_error_fields(exc)
                    logger.error(
                        "Voyage embedding failed type=%s status=%s code=%s request_id=%s "
                        "attempt=%d/%d",
                        error_type,
                        status_code,
                        code,
                        request_id,
                        attempt + 1,
                        self.max_retries + 1,
                    )
                    raise EmbeddingProviderError(
                        "Voyage could not create document embeddings."
                    ) from exc
                provider_delay = self._retry_after_seconds(exc) or 0.0
                delay = max(
                    min(self.retry_base_seconds * (2**attempt), 60.0),
                    provider_delay,
                )
                status_code, code, request_id, error_type = self._provider_error_fields(exc)
                logger.warning(
                    "Voyage embedding transient failure type=%s status=%s code=%s "
                    "request_id=%s; retrying in %.1f seconds",
                    error_type,
                    status_code,
                    code,
                    request_id,
                    delay,
                )
                self.sleep(delay)
        raise EmbeddingProviderError("Voyage could not create document embeddings.")

    def _reserve_provider_request(self, token_count: int) -> None:
        if token_count > self.tokens_per_minute:
            raise EmbeddingError("An embedding batch exceeds the provider token-minute limit.")

        while True:
            now = self.clock()
            cutoff = now - 60.0
            while self._request_history and self._request_history[0].timestamp <= cutoff:
                self._request_history.popleft()

            used_tokens = sum(usage.token_count for usage in self._request_history)
            request_allowed = len(self._request_history) < self.requests_per_minute
            tokens_allowed = used_tokens + token_count <= self.tokens_per_minute
            if request_allowed and tokens_allowed:
                self._request_history.append(_RequestUsage(now, token_count))
                return

            request_wait = 0.0
            if not request_allowed:
                request_wait = self._request_history[0].timestamp + 60.0 - now

            token_wait = 0.0
            if not tokens_allowed:
                remaining_tokens = used_tokens
                for usage in self._request_history:
                    remaining_tokens -= usage.token_count
                    if remaining_tokens + token_count <= self.tokens_per_minute:
                        token_wait = usage.timestamp + 60.0 - now
                        break

            delay = max(0.001, request_wait, token_wait)
            logger.info(
                "Waiting %.1f seconds for Voyage rolling limits (%d requests, %d budgeted tokens)",
                delay,
                len(self._request_history),
                used_tokens,
            )
            self.sleep(delay)

    def embed_documents(self, texts: list[str], token_counts: list[int]) -> list[list[float]]:
        if not texts or len(texts) != len(token_counts):
            raise EmbeddingError("Embedding inputs and token counts must be non-empty and aligned.")

        budget_token_counts = self._budget_token_counts(texts, token_counts)
        batches = self._make_batches(texts, budget_token_counts)
        vectors: list[list[float]] = []
        with self._request_lock:
            for index, batch in enumerate(batches, start=1):
                logger.info(
                    "Embedding Voyage batch %d/%d (%d chunks, %d budgeted tokens)",
                    index,
                    len(batches),
                    len(batch.texts),
                    batch.token_count,
                )
                batch_vectors = self._embed_batch(batch, input_type="document")
                if len(batch_vectors) != len(batch.texts):
                    raise EmbeddingError(
                        "Voyage returned a different number of vectors than inputs."
                    )
                if any(len(vector) != self.dimensions for vector in batch_vectors):
                    raise EmbeddingError(
                        "Voyage returned an embedding with dimensions other than "
                        f"{self.dimensions}."
                    )
                vectors.extend(batch_vectors)

        if len(vectors) != len(texts):
            raise EmbeddingError("Embedding output order could not be validated.")
        return vectors

    def embed_query(self, question: str) -> list[float]:
        normalized_question = question.strip()
        if not normalized_question:
            raise EmbeddingError("A non-empty question is required for query embedding.")

        estimated_tokens = max(1, len(normalized_question.split()) * 2)
        budget_token_count = self._budget_token_counts(
            [normalized_question],
            [estimated_tokens],
        )[0]
        batch = _EmbeddingBatch([normalized_question], budget_token_count)
        with self._request_lock:
            vectors = self._embed_batch(batch, input_type="query")

        if len(vectors) != 1 or len(vectors[0]) != self.dimensions:
            raise EmbeddingError(
                "Voyage returned an invalid query embedding shape."
            )
        return vectors[0]


@lru_cache(maxsize=1)
def get_embedding_service() -> VoyageEmbeddingService:
    return VoyageEmbeddingService()
