from __future__ import annotations

from typing import Any, Literal, Mapping

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class ResearchRequest(BaseModel):
    query: str
    max_results: int
    categories: list[str] | None = None
    sort_by: Literal["relevance", "lastUpdatedDate"] = "relevance"
    mode: Literal["live", "replay"] = "live"

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must be non-empty.")
        return normalized

    @field_validator("max_results")
    @classmethod
    def validate_max_results(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_results must be >= 1.")
        return value

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized: list[str] = []
        for item in value:
            normalized_item = item.strip()
            if not normalized_item:
                raise ValueError("categories entries must be non-empty.")
            normalized.append(normalized_item)
        return normalized


class ResearchPaper(BaseModel):
    paper_id: str
    title: str
    authors: list[str]
    abstract: str
    categories: list[str]
    published: str

    @field_validator("paper_id", "title", "abstract", "published")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ResearchPaper string fields must be non-empty.")
        return normalized

    @field_validator("authors", "categories")
    @classmethod
    def validate_string_lists(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            normalized_item = item.strip()
            if not normalized_item:
                raise ValueError("ResearchPaper list entries must be non-empty.")
            normalized.append(normalized_item)
        return normalized


class DigestBullet(BaseModel):
    text: str
    cited_paper_ids: list[str] = Field(default_factory=list)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("text must be non-empty.")
        return normalized

    @field_validator("cited_paper_ids")
    @classmethod
    def validate_cited_paper_ids(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            normalized_item = item.strip()
            if not normalized_item:
                raise ValueError("cited_paper_ids entries must be non-empty.")
            normalized.append(normalized_item)
        return normalized


class SynthesisHighlights(BaseModel):
    query: str | None = None
    highlights: list[DigestBullet] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def validate_optional_query(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must be non-empty when provided.")
        return normalized


class ResearchDigest(BaseModel):
    query: str
    generated_at_utc: AwareDatetime
    papers: list[ResearchPaper] = Field(default_factory=list)
    highlights: list[DigestBullet] = Field(default_factory=list)

    @field_validator("query")
    @classmethod
    def validate_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("query must be non-empty.")
        return normalized


def parse_research_digest(payload: Mapping[str, Any]) -> ResearchDigest:
    """Runtime output contract gate for research digest payloads."""
    return ResearchDigest.model_validate(dict(payload))
