from pathlib import Path

import pytest

from app.services.pdf_extraction import (
    InsufficientExtractableTextError,
    extract_pdf_pages,
)


def test_extracts_pages_with_human_page_numbers_and_keeps_empty_pages(
    tmp_path: Path,
    make_pdf,
) -> None:
    path = make_pdf(
        tmp_path / "lease.pdf",
        [
            "RESIDENTIAL LEASE\n\nThe tenant agrees to pay monthly rent on time.",
            None,
            "REPAIRS\n\nThe landlord will maintain the heating system.",
        ],
    )

    pages = extract_pdf_pages(path, minimum_characters=10)

    assert [page.page_number for page in pages] == [1, 2, 3]
    assert "monthly rent" in pages[0].text
    assert pages[1].text == ""
    assert "heating system" in pages[2].text


def test_image_only_or_blank_pdf_has_useful_error(tmp_path: Path, make_pdf) -> None:
    path = make_pdf(tmp_path / "blank.pdf", [None, None])

    with pytest.raises(InsufficientExtractableTextError, match="OCR"):
        extract_pdf_pages(path)
