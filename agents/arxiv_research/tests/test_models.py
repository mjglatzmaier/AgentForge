from __future__ import annotations

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agents.arxiv_research.models import (
    DigestBullet,
    ResearchDigest,
    ResearchPaper,
    ResearchRequest,
    SynthesisHighlights,
    parse_research_digest,
)


def _paper_payload() -> dict:
    return {
        "paper_id": "1234.5678",
        "title": "A Paper",
        "authors": ["Alice", "Bob"],
        "abstract": "Summary",
        "categories": ["cs.AI"],
        "published": "2026-01-01T00:00:00Z",
    }


def test_research_request_valid_payload() -> None:
    request = ResearchRequest(
        query="transformers",
        max_results=5,
        categories=["cs.AI"],
        sort_by="relevance",
        mode="live",
    )
    assert request.query == "transformers"
    assert request.max_results == 5


def test_research_request_rejects_invalid_literals_and_limits() -> None:
    with pytest.raises(ValidationError, match="max_results must be >= 1"):
        ResearchRequest(query="q", max_results=0, sort_by="relevance", mode="live")

    with pytest.raises(ValidationError):
        ResearchRequest(query="q", max_results=1, sort_by="invalid", mode="live")

    with pytest.raises(ValidationError):
        ResearchRequest(query="q", max_results=1, sort_by="relevance", mode="invalid")


def test_research_digest_models_validate_expected_shape() -> None:
    digest = ResearchDigest(
        query="transformers",
        generated_at_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        papers=[ResearchPaper.model_validate(_paper_payload())],
        highlights=[DigestBullet(text="Key finding", cited_paper_ids=["1234.5678"])],
    )
    assert digest.papers[0].paper_id == "1234.5678"
    assert digest.highlights[0].cited_paper_ids == ["1234.5678"]


def test_research_digest_serialization_is_deterministic() -> None:
    payload = {
        "query": "transformers",
        "generated_at_utc": "2026-01-01T00:00:00Z",
        "papers": [_paper_payload()],
        "highlights": [{"text": "Key finding", "cited_paper_ids": ["1234.5678"]}],
    }
    digest_a = ResearchDigest.model_validate(payload)
    digest_b = ResearchDigest.model_validate(payload)
    assert digest_a.model_dump(mode="json") == digest_b.model_dump(mode="json")
    assert digest_a.model_dump_json() == digest_b.model_dump_json()


def test_parse_research_digest_enforces_output_contract_at_runtime() -> None:
    with pytest.raises(ValidationError):
        parse_research_digest(
            {
                "query": "x",
                "generated_at_utc": "2026-01-01T00:00:00Z",
                "papers": [{"paper_id": "id-only"}],
                "highlights": [],
            }
        )


def test_synthesis_highlights_model_accepts_query_and_highlights() -> None:
    highlights = SynthesisHighlights(
        query="agent systems",
        highlights=[DigestBullet(text="Key finding", cited_paper_ids=["1234.5678"])],
    )
    assert highlights.query == "agent systems"
    assert highlights.highlights[0].cited_paper_ids == ["1234.5678"]


def test_synthesis_highlights_rejects_blank_query_when_provided() -> None:
    with pytest.raises(ValidationError, match="query must be non-empty when provided"):
        SynthesisHighlights(query="   ", highlights=[])
