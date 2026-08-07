import uuid

from pydantic import BaseModel, Field, field_validator


class QuestionRequest(BaseModel):
    question: str = Field(min_length=1, max_length=1_000)

    @field_validator("question")
    @classmethod
    def normalize_question(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Question must not be blank.")
        return normalized


class RetrievedChunkResponse(BaseModel):
    chunk_id: uuid.UUID
    chunk_index: int
    page_number: int
    section_title: str | None
    text: str
    score: float


class RetrievalResponse(BaseModel):
    results: list[RetrievedChunkResponse]


class CitationResponse(BaseModel):
    chunk_id: uuid.UUID
    page_number: int
    section_title: str | None
    snippet: str
    score: float


class QuestionResponse(BaseModel):
    answer: str
    citations: list[CitationResponse]
