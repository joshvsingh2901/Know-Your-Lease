from app.services.chunking import chunk_pages, estimate_token_count
from app.services.pdf_extraction import ExtractedPage


def test_chunking_is_page_scoped_ordered_nonempty_and_bounded() -> None:
    paragraphs = [
        (
            f"Clause {index}. The tenant must provide written notice before making a change "
            "to the premises, and the landlord must respond within a reasonable period. "
            "This paragraph preserves enough neighboring legal context for retrieval."
        )
        for index in range(45)
    ]
    pages = [
        ExtractedPage(page_number=1, text="\n\n".join(paragraphs)),
        ExtractedPage(page_number=2, text="\n\n".join(paragraphs[:8])),
    ]

    chunks = chunk_pages(
        pages,
        target_tokens=180,
        max_tokens=220,
        overlap_tokens=25,
        min_tokens=60,
    )

    assert len(chunks) > 3
    assert [chunk.chunk_index for chunk in chunks] == list(range(len(chunks)))
    assert {chunk.page_number for chunk in chunks} == {1, 2}
    assert all(chunk.text.strip() for chunk in chunks)
    assert all(chunk.token_count == estimate_token_count(chunk.text) for chunk in chunks)
    assert all(chunk.token_count <= 220 for chunk in chunks)
    assert all(chunk.paragraph_index is not None for chunk in chunks)


def test_chunking_never_combines_pages() -> None:
    chunks = chunk_pages(
        [
            ExtractedPage(1, "Page one obligation. " * 80),
            ExtractedPage(2, "Page two obligation. " * 80),
        ],
        target_tokens=100,
        max_tokens=120,
        overlap_tokens=10,
        min_tokens=40,
    )

    assert chunks
    assert all(
        not ("Page one" in chunk.text and "Page two" in chunk.text)
        for chunk in chunks
    )


def test_chunk_overlap_repeats_complete_context_units() -> None:
    text = " ".join(
        f"The tenant obligation number {index} requires written notice before alterations."
        for index in range(30)
    )
    chunks = chunk_pages(
        [ExtractedPage(1, text)],
        target_tokens=80,
        max_tokens=100,
        overlap_tokens=20,
        min_tokens=30,
    )

    assert len(chunks) > 1
    repeated_sentence = chunks[1].text.split(". ", maxsplit=1)[0] + "."
    assert repeated_sentence in chunks[0].text
