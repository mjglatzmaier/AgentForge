from __future__ import annotations

from typing import Protocol

from agents.arxiv_research.models import ResearchPaper
from agents.arxiv_research.scoring.models import ScoringConfig

JsonScalar = str | int | float | bool | None


class EnrichmentAdapter(Protocol):
    def fetch_signals(
        self, papers: list[ResearchPaper], *, config: ScoringConfig
    ) -> dict[str, dict[str, JsonScalar]]: ...


class HeuristicEnrichmentAdapter:
    """Deterministic local enrichment adapter (network-free)."""

    def fetch_signals(
        self, papers: list[ResearchPaper], *, config: ScoringConfig
    ) -> dict[str, dict[str, JsonScalar]]:
        _ = config
        signals: dict[str, dict[str, JsonScalar]] = {}
        for paper in papers:
            text = f"{paper.title} {paper.abstract}".lower()
            signals[paper.paper_id] = {
                "has_code_reference": ("github" in text or "code" in text),
                "has_doi_reference": ("doi:" in text or "doi.org/" in text),
                "abstract_char_count": len(paper.abstract),
            }
        return signals


def resolve_enrichment_adapter(config: ScoringConfig) -> EnrichmentAdapter:
    source = (config.enrichment.source or "heuristic_v1").strip().lower()
    if source in {"heuristic_v1", "local"}:
        return HeuristicEnrichmentAdapter()
    raise ValueError(f"Unsupported enrichment source: {config.enrichment.source}")
