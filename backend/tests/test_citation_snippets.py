import pytest

from app.services.citation_snippets import (
    MAX_SNIPPET_CHARS,
    build_citation_snippet,
    is_trustworthy_section_title,
)


@pytest.mark.parametrize("title", ["or", "f)", ".", ":", "i.", "Select one"])
def test_junk_section_titles_are_rejected(title: str) -> None:
    assert is_trustworthy_section_title(title) is False


@pytest.mark.parametrize(
    "title",
    ["Pets", "Rent Discounts", "Services and Utilities", "Landlord's Entry into Rental Unit"],
)
def test_legitimate_section_titles_are_accepted(title: str) -> None:
    assert is_trustworthy_section_title(title) is True


def test_junk_provided_title_falls_back_to_page_only() -> None:
    citation = build_citation_snippet(
        question="What fees apply?",
        chunk_text="The tenant must pay a $20 administration fee for an NSF cheque.",
        section_title="f)",
    )

    assert citation.section_title is None


def test_matching_model_quote_is_used_as_the_citation_snippet() -> None:
    chunk = (
        "Q. Guests (Part III of the Act) Guests are permitted. "
        "R. Pets (Part III of the Act) A tenancy agreement cannot prohibit animals "
        "in the rental unit."
    )

    citation = build_citation_snippet(
        question="Can I have pets?",
        chunk_text=chunk,
        model_quote="A tenancy agreement cannot prohibit animals in the rental unit.",
    )

    assert citation.used_model_quote is True
    assert citation.text == "A tenancy agreement cannot prohibit animals in the rental unit."
    assert citation.section_title == "Pets"


def test_invalid_model_quote_uses_a_deterministic_relevant_fallback() -> None:
    chunk = (
        "Guests are permitted. Pets must be kept on a leash in common areas. "
        "Smoking is prohibited."
    )

    citation = build_citation_snippet(
        question="Can I have pets?",
        chunk_text=chunk,
        model_quote="Pets are allowed everywhere without restrictions.",
    )

    assert citation.used_model_quote is False
    assert "Pets must be kept on a leash" in citation.text
    assert "allowed everywhere" not in citation.text


def test_whitespace_normalized_model_quote_is_accepted() -> None:
    citation = build_citation_snippet(
        question="Can I have pets?",
        chunk_text="Pets are allowed in the unit.\n\nThey must be kept on a leash.",
        model_quote="Pets are allowed   in the unit. They must be kept on a leash.",
    )

    assert citation.used_model_quote is True
    assert citation.text == "Pets are allowed in the unit. They must be kept on a leash."


def test_explicit_nearby_heading_is_used_without_fabrication() -> None:
    citation = build_citation_snippet(
        question="Can I have pets?",
        chunk_text=(
            "Garbage/Recycling\n\nAll garbage must be bagged.\n\nPets\n\n"
            "The Tenant agrees to not allow pets in suite common areas."
        ),
        model_quote="The Tenant agrees to not allow pets in suite common areas.",
    )

    assert citation.section_title == "Pets"


def test_fallback_snippet_is_bounded_without_returning_the_whole_chunk() -> None:
    unrelated = "Unrelated administrative clause. " * 80
    chunk = f"{unrelated}Pets must be kept on a leash in common areas."

    citation = build_citation_snippet(
        question="Can I have pets?",
        chunk_text=chunk,
    )

    assert len(citation.text) <= MAX_SNIPPET_CHARS
    assert "Pets must be kept on a leash" in citation.text
    assert citation.text != " ".join(chunk.split())
