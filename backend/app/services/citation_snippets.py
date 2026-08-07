import re
from dataclasses import dataclass

MAX_SNIPPET_CHARS = 480
_WHITESPACE = re.compile(r"\s+")
_WORD = re.compile(r"[\w'-]+")
_SENTENCE_BOUNDARY = re.compile(r"(?<![A-Z])(?<=[.!?])\s+(?=[A-Z0-9])")
_LETTERED_SECTION = re.compile(
    r"\b[A-Z]\.\s+([A-Z][A-Za-z &'/-]{0,70}?)(?=\s+\(Part\b)"
)
_SHORT_LINE_HEADING = re.compile(r"[A-Za-z][A-Za-z &'()/,-]{0,78}\Z")
_LETTERED_PREFIX = re.compile(r"^[A-Z]\.\s+")
_OPTION_LABEL = re.compile(r"(?i)(?:[a-z]|[ivxlcdm]+|option)\)?\.?\Z")
_MEANINGLESS_HEADINGS = frozenset(
    {"and", "or", "no", "none", "n/a", "not applicable", "select one", "yes"}
)
_QUESTION_STOPWORDS = frozenset(
    {
        "a",
        "about",
        "an",
        "and",
        "are",
        "can",
        "do",
        "does",
        "for",
        "have",
        "i",
        "if",
        "in",
        "is",
        "know",
        "landlord",
        "lease",
        "me",
        "my",
        "of",
        "or",
        "the",
        "to",
        "unit",
        "what",
        "when",
        "with",
        "you",
    }
)


@dataclass(frozen=True)
class CitationSnippet:
    text: str
    section_title: str | None
    used_model_quote: bool


def _normalize(value: str) -> str:
    return _WHITESPACE.sub(" ", value).strip()


def validate_section_title(value: str | None) -> str | None:
    """Return only a source-derived heading that is useful in a citation card."""
    candidate = _normalize(value or "")
    candidate = _LETTERED_PREFIX.sub("", candidate)
    lowered = candidate.casefold()
    word_count = len(re.findall(r"[A-Za-z]{2,}", candidate))

    if (
        len(candidate) < 3
        or len(candidate) > 80
        or lowered in _MEANINGLESS_HEADINGS
        or "select one" in lowered
        or _OPTION_LABEL.fullmatch(candidate) is not None
        or word_count == 0
        or not candidate[0].isupper()
        or candidate.endswith((".", ";", ":"))
    ):
        return None
    return candidate


def is_trustworthy_section_title(value: str | None) -> bool:
    return validate_section_title(value) is not None


def _sentence_parts(text: str) -> list[str]:
    normalized = _normalize(text)
    return [part.strip() for part in _SENTENCE_BOUNDARY.split(normalized) if part.strip()]


def _bounded_sentences(parts: list[str], preferred_index: int) -> str:
    selected = [parts[preferred_index]]
    for neighbor_index in (preferred_index + 1, preferred_index - 1):
        if not 0 <= neighbor_index < len(parts):
            continue
        candidate = (
            [parts[neighbor_index], *selected]
            if neighbor_index < preferred_index
            else [*selected, parts[neighbor_index]]
        )
        if len(" ".join(candidate)) <= MAX_SNIPPET_CHARS:
            selected = candidate

    snippet = " ".join(selected)
    if len(snippet) <= MAX_SNIPPET_CHARS:
        return snippet

    # A very long legal sentence is unusual, but retain a whole-word, useful prefix
    # instead of returning the full retrieval chunk.
    cutoff = snippet.rfind(" ", 0, MAX_SNIPPET_CHARS - 1)
    return f"{snippet[: cutoff if cutoff > 0 else MAX_SNIPPET_CHARS - 1].rstrip()}…"


def _fallback_snippet(question: str, chunk_text: str) -> str:
    parts = _sentence_parts(chunk_text)
    if not parts:
        return ""

    query_terms = {
        token.casefold()
        for token in _WORD.findall(question)
        if len(token) > 1 and token.casefold() not in _QUESTION_STOPWORDS
    }

    def score(part: str) -> tuple[int, int]:
        words = {token.casefold() for token in _WORD.findall(part)}
        return (len(query_terms & words), -len(part))

    best_index = max(range(len(parts)), key=lambda index: score(parts[index]))
    return _bounded_sentences(parts, best_index)


def _infer_section_title(chunk_text: str, snippet: str) -> str | None:
    normalized_snippet = _normalize(snippet)
    snippet_pattern = re.escape(normalized_snippet[:100]).replace(r"\ ", r"\s+")
    raw_match = re.search(snippet_pattern, chunk_text, flags=re.IGNORECASE)
    if raw_match is not None:
        for line in reversed(chunk_text[: raw_match.start()].splitlines()):
            candidate = _normalize(line)
            if (
                candidate
                and _SHORT_LINE_HEADING.fullmatch(candidate)
                and not candidate.endswith((".", ";", ":"))
            ):
                trusted_candidate = validate_section_title(candidate)
                if trusted_candidate:
                    return trusted_candidate

    normalized_chunk = _normalize(chunk_text)
    snippet_position = normalized_chunk.casefold().find(normalized_snippet.casefold())
    if snippet_position < 0:
        return None

    heading: str | None = None
    for match in _LETTERED_SECTION.finditer(normalized_chunk):
        if match.start() > snippet_position:
            break
        heading = match.group(1).strip()
    return validate_section_title(heading)


def build_citation_snippet(
    *,
    question: str,
    chunk_text: str,
    model_quote: str | None = None,
    section_title: str | None = None,
) -> CitationSnippet:
    """Return a bounded human-facing excerpt without modifying retrieval evidence."""
    normalized_chunk = _normalize(chunk_text)
    normalized_quote = _normalize(model_quote or "")
    quote_is_valid = bool(
        normalized_quote and normalized_quote.casefold() in normalized_chunk.casefold()
    )

    if quote_is_valid:
        quote_parts = _sentence_parts(normalized_quote)
        snippet = _bounded_sentences(quote_parts, 0) if quote_parts else normalized_quote
    else:
        snippet = _fallback_snippet(question, chunk_text)

    if not snippet:
        # Question-answering only supplies non-empty chunk text. This is a final
        # defensive fallback that still never exposes more than a short excerpt.
        snippet = _normalize(chunk_text)[:MAX_SNIPPET_CHARS].rstrip()

    return CitationSnippet(
        text=snippet,
        section_title=validate_section_title(section_title)
        or _infer_section_title(chunk_text, snippet),
        used_model_quote=quote_is_valid,
    )
