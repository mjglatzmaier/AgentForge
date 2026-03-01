from __future__ import annotations

from datetime import datetime, timezone

from agents.arxiv_research.models import ResearchPaper
from agents.arxiv_research.scoring.features import (
    compute_feature_scores,
    compute_feature_scores_for_paper,
)
from agents.arxiv_research.scoring.models import ScoringConfig


def _paper(*, published: str, abstract: str, title: str = "Agent Scaling Laws") -> ResearchPaper:
    return ResearchPaper(
        paper_id="2401.00001v1",
        title=title,
        authors=["Alice"],
        abstract=abstract,
        categories=["cs.AI", "cs.LG"],
        published=published,
    )


def test_compute_feature_scores_for_paper_is_bounded_and_explained() -> None:
    config = ScoringConfig(
        topic_alignment={"keywords": ["agent"], "phrases": ["scaling laws"]},
        methodological_rigor={"experiment_terms": ["ablation"], "theory_terms": ["theorem"]},
        engagement={"proxy_terms": ["github"], "proxy_bonus_per_hit": 0.1, "max_proxy_bonus": 0.2},
    )
    paper = _paper(
        published="2026-01-01T00:00:00Z",
        abstract="Includes ablation study, theorem, code on GitHub, and DOI:10.1000/x.",
    )
    scores = compute_feature_scores_for_paper(
        paper, config, now_utc=datetime(2026, 1, 2, tzinfo=timezone.utc)
    )
    assert 0.0 <= scores.topic_alignment <= 1.0
    assert 0.0 <= scores.recency <= 1.0
    assert 0.0 <= scores.credibility <= 1.0
    assert 0.0 <= scores.methodological_rigor <= 1.0
    assert 0.0 <= scores.engagement <= 1.0
    assert set(scores.factor_explanations) == {
        "topic_alignment",
        "recency",
        "credibility",
        "methodological_rigor",
        "engagement",
    }


def test_topic_alignment_uses_keywords_phrases_and_category_bonus() -> None:
    config = ScoringConfig(
        topic_alignment={
            "keywords": ["agent"],
            "phrases": ["scaling laws"],
            "title_weight": 2.0,
            "abstract_weight": 1.0,
            "category_bonus": 0.25,
        }
    )
    paper = ResearchPaper(
        paper_id="2401.00002v1",
        title="Scaling Laws for Agentic Systems",
        authors=["Bob"],
        abstract="This paper studies scaling laws for agent workflows.",
        categories=["llm-agentics"],
        published="2026-01-01T00:00:00Z",
    )
    scores = compute_feature_scores_for_paper(
        paper, config, now_utc=datetime(2026, 1, 2, tzinfo=timezone.utc)
    )
    assert scores.topic_alignment > 0.5


def test_recency_decays_with_age_deterministically() -> None:
    config = ScoringConfig(recency={"half_life_days": 30})
    now = datetime(2026, 2, 1, tzinfo=timezone.utc)
    recent = _paper(published="2026-01-25T00:00:00Z", abstract="x")
    old = _paper(published="2024-01-01T00:00:00Z", abstract="x", title="Older")
    recent_score = compute_feature_scores_for_paper(recent, config, now_utc=now).recency
    old_score = compute_feature_scores_for_paper(old, config, now_utc=now).recency
    assert recent_score > old_score
    assert compute_feature_scores_for_paper(recent, config, now_utc=now).recency == recent_score


def test_credibility_rigor_and_engagement_proxies_work() -> None:
    config = ScoringConfig(
        credibility={"doi_bonus": 0.2, "journal_ref_bonus": 0.2},
        methodological_rigor={"experiment_terms": ["ablation"], "theory_terms": ["theorem"]},
        engagement={"proxy_terms": ["github", "dataset"], "proxy_bonus_per_hit": 0.2, "max_proxy_bonus": 0.4},
    )
    paper = _paper(
        published="2026-01-01T00:00:00Z",
        abstract="Ablation and theorem included. DOI:10.1/x. Published in Journal; code on GitHub and dataset released.",
    )
    scores = compute_feature_scores_for_paper(
        paper, config, now_utc=datetime(2026, 1, 2, tzinfo=timezone.utc)
    )
    assert scores.credibility > 0.0
    assert scores.methodological_rigor > 0.0
    assert scores.engagement > 0.0


def test_recency_invalid_published_returns_zero() -> None:
    config = ScoringConfig()
    paper = _paper(published="not-a-date", abstract="x")
    scores = compute_feature_scores_for_paper(
        paper, config, now_utc=datetime(2026, 1, 2, tzinfo=timezone.utc)
    )
    assert scores.recency == 0.0


def test_compute_feature_scores_list_is_deterministic() -> None:
    config = ScoringConfig()
    papers = [
        _paper(published="2026-01-01T00:00:00Z", abstract="first"),
        _paper(published="2026-01-02T00:00:00Z", abstract="second", title="Paper Two"),
    ]
    now = datetime(2026, 1, 3, tzinfo=timezone.utc)
    scores_a = compute_feature_scores(papers, config, now_utc=now)
    scores_b = compute_feature_scores(papers, config, now_utc=now)
    assert [item.model_dump(mode="json") for item in scores_a] == [
        item.model_dump(mode="json") for item in scores_b
    ]
