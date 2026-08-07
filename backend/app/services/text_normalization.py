import re

HORIZONTAL_WHITESPACE = re.compile(r"[^\S\n]+")
BLANK_LINES = re.compile(r"\n\s*\n(?:\s*\n)+")


def normalize_page_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\u00a0", " ")
    paragraphs: list[str] = []
    for raw_paragraph in re.split(r"\n\s*\n", text):
        lines = [HORIZONTAL_WHITESPACE.sub(" ", line).strip() for line in raw_paragraph.splitlines()]
        paragraph = " ".join(line for line in lines if line)
        if paragraph:
            paragraphs.append(paragraph)
    return BLANK_LINES.sub("\n\n", "\n\n".join(paragraphs)).strip()
