from __future__ import annotations

from agents.arxiv_research.models import ResearchPaper
from agents.arxiv_research.scoring.aggregate import aggregate_scored_papers, normalize_weights
from agents.arxiv_research.scoring.models import PaperFeatureScores, ScoringConfig, ScoringWeights
from agents.arxiv_research.scoring.select import (
    build_scoring_payload,
    order_scored_papers,
    select_scored_papers,
)


def _paper(*, paper_id: str, published: str) -> ResearchPaper:
    return ResearchPaper(
        paper_id=paper_id,
        title=f"Paper {paper_id}",
        authors=["Alice"],
        abstract="Summary",
        categories=["cs.AI"],
        published=published,
    )


def _features(
    *,
    paper_id: str,
    topic_alignment: float,
    recency: float,
    credibility: float,
    methodological_rigor: float,
    engagement: float,
) -> PaperFeatureScores:
    return PaperFeatureScores(
        paper_id=paper_id,
        topic_alignment=topic_alignment,
        recency=recency,
        credibility=credibility,
        methodological_rigor=methodological_rigor,
        engagement=engagement,
    )


def test_normalize_weights_produces_unit_sum() -> None:
    normalized = normalize_weights(
        ScoringWeights(
            topic_alignment=2.0,
            recency=1.0,
            credibility=1.0,
            methodological_rigor=0.0,
            engagement=0.0,
        )
    )
    total = (
        normalized.topic_alignment
        + normalized.recency
        + normalized.credibility
        + normalized.methodological_rigor
        + normalized.engagement
    )
    assert round(total, 10) == 1.0


def test_aggregate_scored_papers_computes_weighted_totals() -> None:
    config = ScoringConfig(
        weights={
            "topic_alignment": 1.0,
            "recency": 0.0,
            "credibility": 0.0,
            "methodological_rigor": 0.0,
            "engagement": 0.0,
        }
    )
    papers = [_paper(paper_id="p1", published="2026-01-01T00:00:00Z")]
    features = [
        _features(
            paper_id="p1",
            topic_alignment=0.8,
            recency=0.1,
            credibility=0.1,
            methodological_rigor=0.1,
            engagement=0.1,
        )
    ]
    scored, diagnostics = aggregate_scored_papers(
        papers=papers, feature_scores=features, config=config
    )
    assert len(scored) == 1
    assert scored[0].score_total == 0.8
    assert diagnostics.candidate_count == 1


def test_order_scored_papers_uses_deterministic_tie_breakers() -> None:
    config = ScoringConfig()
    papers = [
        _paper(paper_id="a", published="2026-01-01T00:00:00Z"),
        _paper(paper_id="b", published="2026-01-02T00:00:00Z"),
        _paper(paper_id="c", published="2026-01-02T00:00:00Z"),
    ]
    features = [
        _features(
            paper_id="a",
            topic_alignment=0.5,
            recency=0.0,
            credibility=0.0,
            methodological_rigor=0.0,
            engagement=0.0,
        ),
        _features(
            paper_id="b",
            topic_alignment=0.5,
            recency=0.0,
            credibility=0.0,
            methodological_rigor=0.0,
            engagement=0.0,
        ),
        _features(
            paper_id="c",
            topic_alignment=0.5,
            recency=0.0,
            credibility=0.0,
            methodological_rigor=0.0,
            engagement=0.0,
        ),
    ]
    scored, _ = aggregate_scored_papers(papers=papers, feature_scores=features, config=config)
    ordered = order_scored_papers(scored, tie_breakers=config.tie_breakers)
    assert [item.paper.paper_id for item in ordered] == ["b", "c", "a"]
    assert [item.rank for item in ordered] == [1, 2, 3]


def test_select_scored_papers_applies_threshold_and_limits() -> None:
    config = ScoringConfig(select_m=2, top_k=1, min_score_threshold=0.4)
    papers = [
        _paper(paper_id="p1", published="2026-01-03T00:00:00Z"),
        _paper(paper_id="p2", published="2026-01-02T00:00:00Z"),
        _paper(paper_id="p3", published="2026-01-01T00:00:00Z"),
    ]
    features = [
        _features(
            paper_id="p1",
            topic_alignment=0.9,
            recency=0.0,
            credibility=0.0,
            methodological_rigor=0.0,
            engagement=0.0,
        ),
        _features(
            paper_id="p2",
            topic_alignment=0.5,
            recency=0.0,
            credibility=0.0,
            methodological_rigor=0.0,
            engagement=0.0,
        ),
        _features(
            paper_id="p3",
            topic_alignment=0.2,
            recency=0.0,
            credibility=0.0,
            methodological_rigor=0.0,
            engagement=0.0,
        ),
    ]
    scored, diagnostics = aggregate_scored_papers(papers=papers, feature_scores=features, config=config)
    ordered = order_scored_papers(scored, tie_breakers=config.tie_breakers)
    selected, diagnostics_updated = select_scored_papers(
        scored_papers=ordered, config=config, diagnostics=diagnostics
    )
    assert [item.paper.paper_id for item in selected] == ["p1"]
    assert diagnostics_updated.selected_count == 1
    assert diagnostics_updated.dropped_below_threshold == 2


def test_build_scoring_payload_contains_contract_keys() -> None:
    config = ScoringConfig()
    papers = [_paper(paper_id="p1", published="2026-01-01T00:00:00Z")]
    features = [
        _features(
            paper_id="p1",
            topic_alignment=0.5,
            recency=0.5,
            credibility=0.5,
            methodological_rigor=0.5,
            engagement=0.5,
        )
    ]
    scored, diagnostics = aggregate_scored_papers(papers=papers, feature_scores=features, config=config)
    ordered = order_scored_papers(scored, tie_breakers=config.tie_breakers)
    selected, updated = select_scored_papers(
        scored_papers=ordered, config=config, diagnostics=diagnostics
    )
    payload = build_scoring_payload(
        scored_papers=ordered, selected_papers=selected, diagnostics=updated
    )
    assert set(payload.keys()) == {"papers_scored", "papers_selected", "scoring_diagnostics"}
    assert payload["papers_scored"][0]["paper"]["paper_id"] == "p1"
