import math
import re
from dataclasses import dataclass

from app.core.config import settings
from app.services.pdf_extraction import ExtractedPage

TOKEN_PATTERN = re.compile(r"\w+(?:[’'-]\w+)*|[^\w\s]", re.UNICODE)
SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?;:])\s+(?=[A-Z0-9(\[])")


@dataclass(frozen=True)
class ChunkDraft:
    chunk_index: int
    text: str
    page_number: int
    paragraph_index: int | None
    section_title: str | None
    token_count: int


@dataclass(frozen=True)
class _TextUnit:
    text: str
    paragraph_index: int
    token_count: int


def estimate_token_count(text: str) -> int:
    lexical_tokens = len(TOKEN_PATTERN.findall(text))
    return max(1, math.ceil(lexical_tokens * 1.1)) if text.strip() else 0


def _split_oversized_text(text: str, max_tokens: int) -> list[str]:
    words = text.split()
    parts: list[str] = []
    current: list[str] = []
    for word in words:
        candidate = " ".join([*current, word])
        if current and estimate_token_count(candidate) > max_tokens:
            parts.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        parts.append(" ".join(current))
    return parts


def _page_units(page: ExtractedPage, max_tokens: int) -> list[_TextUnit]:
    units: list[_TextUnit] = []
    paragraphs = [paragraph.strip() for paragraph in page.text.split("\n\n") if paragraph.strip()]
    for paragraph_index, paragraph in enumerate(paragraphs):
        sentences = [part.strip() for part in SENTENCE_BOUNDARY.split(paragraph) if part.strip()]
        for sentence in sentences or [paragraph]:
            parts = (
                _split_oversized_text(sentence, max_tokens)
                if estimate_token_count(sentence) > max_tokens
                else [sentence]
            )
            units.extend(
                _TextUnit(
                    text=part,
                    paragraph_index=paragraph_index,
                    token_count=estimate_token_count(part),
                )
                for part in parts
                if part.strip()
            )
    return units


def _render_units(units: list[_TextUnit]) -> str:
    pieces: list[str] = []
    previous_paragraph: int | None = None
    for unit in units:
        separator = "\n\n" if previous_paragraph is not None and unit.paragraph_index != previous_paragraph else " "
        if not pieces:
            separator = ""
        pieces.append(f"{separator}{unit.text}")
        previous_paragraph = unit.paragraph_index
    return "".join(pieces).strip()


def _overlap_tail(units: list[_TextUnit], overlap_tokens: int) -> list[_TextUnit]:
    tail: list[_TextUnit] = []
    total = 0
    for unit in reversed(units):
        if total + unit.token_count > overlap_tokens:
            break
        tail.append(unit)
        total += unit.token_count
    return list(reversed(tail))


def chunk_pages(
    pages: list[ExtractedPage],
    *,
    target_tokens: int | None = None,
    max_tokens: int | None = None,
    overlap_tokens: int | None = None,
    min_tokens: int | None = None,
) -> list[ChunkDraft]:
    target = target_tokens or settings.chunk_target_tokens
    maximum = max_tokens or settings.chunk_max_tokens
    overlap = settings.chunk_overlap_tokens if overlap_tokens is None else overlap_tokens
    minimum = min_tokens or settings.chunk_min_tokens
    if not 0 <= overlap < target <= maximum:
        raise ValueError("Chunk token settings must satisfy 0 <= overlap < target <= max.")

    drafts: list[ChunkDraft] = []
    for page in pages:
        page_number = page.page_number
        units = _page_units(page, maximum)
        if not units:
            continue

        current: list[_TextUnit] = []
        current_tokens = 0

        def flush(bound_page_number: int = page_number) -> None:
            nonlocal current, current_tokens
            if not current:
                return
            text = _render_units(current)
            drafts.append(
                ChunkDraft(
                    chunk_index=len(drafts),
                    text=text,
                    page_number=bound_page_number,
                    paragraph_index=current[0].paragraph_index,
                    section_title=None,
                    token_count=estimate_token_count(text),
                )
            )
            current = _overlap_tail(current, overlap)
            current_tokens = sum(unit.token_count for unit in current)

        for unit in units:
            would_exceed_target = current_tokens + unit.token_count > target
            would_exceed_max = current_tokens + unit.token_count > maximum
            if current and (would_exceed_max or (would_exceed_target and current_tokens >= minimum)):
                flush()
            current.append(unit)
            current_tokens += unit.token_count
        flush()

    return [draft for draft in drafts if draft.text.strip()]
