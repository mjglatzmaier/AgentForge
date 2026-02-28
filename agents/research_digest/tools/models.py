from __future__ import annotations

from pydantic import BaseModel, Field


class ArxivPaper(BaseModel):
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str
    url: str
    published: str


class RSSItem(BaseModel):
    title: str
    url: str
    snippet: str
    published: str


class Doc(BaseModel):
    doc_id: str
    title: str
    url: str
    summary: str
    published: str | None = None
    source: str
    score: float = 0.0


class DigestItem(BaseModel):
    doc_id: str
    title: str
    url: str
    summary: str
    source: str
    score: float
    published: str | None = None
    citations: list[str] = Field(default_factory=list)


class Digest(BaseModel):
    title: str = "Research Digest"
    generated_at: str
    items: list[DigestItem] = Field(default_factory=list)
