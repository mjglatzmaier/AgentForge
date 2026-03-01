from __future__ import annotations

from typing import Mapping

from agents.arxiv_research.models import ResearchPaper
from agents.arxiv_research.scoring.models import (
    PaperFeatureScores,
    ScoredPaper,
    ScoringConfig,
    ScoringDiagnostics,
    ScoringWeights,
)


def normalize_weights(weights: ScoringWeights) -> ScoringWeights:
    total = (
        weights.topic_alignment
        + weights.recency
        + weights.credibility
        + weights.methodological_rigor
        + weights.engagement
    )
    return ScoringWeights(
        topic_alignment=weights.topic_alignment / total,
        recency=weights.recency / total,
        credibility=weights.credibility / total,
        methodological_rigor=weights.methodological_rigor / total,
        engagement=weights.engagement / total,
    )


def aggregate_scored_papers(
    *,
    papers: list[ResearchPaper],
    feature_scores: list[PaperFeatureScores],
    config: ScoringConfig,
) -> tuple[list[ScoredPaper], ScoringDiagnostics]:
    features_by_paper_id = _features_index(feature_scores)
    weights = normalize_weights(config.weights)

    scored: list[ScoredPaper] = []
    for paper in papers:
        features = features_by_paper_id.get(paper.paper_id)
        if features is None:
            raise ValueError(f"Missing feature scores for paper_id={paper.paper_id}")
        score_total = (
            (weights.topic_alignment * features.topic_alignment)
            + (weights.recency * features.recency)
            + (weights.credibility * features.credibility)
            + (weights.methodological_rigor * features.methodological_rigor)
            + (weights.engagement * features.engagement)
        )
        scored.append(
            ScoredPaper(
                paper=paper,
                feature_scores=features,
                score_total=score_total,
            )
        )

    diagnostics = ScoringDiagnostics(
        scorer_version=config.scorer_version,
        weights_normalized=weights,
        candidate_count=len(papers),
        selected_count=0,
        dropped_below_threshold=0,
        notes=[],
    )
    return scored, diagnostics


def _features_index(
    feature_scores: list[PaperFeatureScores],
) -> Mapping[str, PaperFeatureScores]:
    by_paper_id: dict[str, PaperFeatureScores] = {}
    for item in feature_scores:
        if item.paper_id in by_paper_id:
            raise ValueError(f"Duplicate feature scores for paper_id={item.paper_id}")
        by_paper_id[item.paper_id] = item
    return by_paper_id
