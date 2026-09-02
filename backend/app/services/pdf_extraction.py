from dataclasses import dataclass
from pathlib import Path

import pymupdf

from app.core.config import settings


class PDFExtractionError(RuntimeError):
    pass


class InsufficientExtractableTextError(PDFExtractionError):
    pass


@dataclass(frozen=True)
class ExtractedPage:
    page_number: int
    text: str


def extract_pdf_pages(
    source: Path | bytes,
    minimum_characters: int | None = None,
) -> list[ExtractedPage]:
    minimum = (
        settings.minimum_extractable_characters
        if minimum_characters is None
        else minimum_characters
    )
    try:
        if isinstance(source, bytes):
            pdf_document = pymupdf.open(stream=source, filetype="pdf")
        else:
            pdf_document = pymupdf.open(source)
        with pdf_document as pdf:
            if pdf.page_count == 0:
                raise PDFExtractionError("The PDF contains no pages.")

            pages: list[ExtractedPage] = []
            for index, page in enumerate(pdf):
                blocks = page.get_text("blocks", sort=True)
                block_text = "\n\n".join(
                    str(block[4]).strip() for block in blocks if str(block[4]).strip()
                )
                pages.append(ExtractedPage(page_number=index + 1, text=block_text))
    except PDFExtractionError:
        raise
    except (pymupdf.FileDataError, RuntimeError, ValueError) as exc:
        raise PDFExtractionError("The PDF could not be read or is corrupted.") from exc

    extracted_characters = sum(len("".join(page.text.split())) for page in pages)
    if extracted_characters < minimum:
        raise InsufficientExtractableTextError(
            "This PDF has little or no extractable text. Scanned or image-only PDFs "
            "require OCR, which is not supported yet."
        )
    return pages
