from __future__ import annotations

import pytest
from pydantic import ValidationError

from agents.arxiv_research.scoring.models import (
    PaperFeatureScores,
    ScoringConfig,
    ScoringWeights,
    scoring_config_from_context,
)


def test_scoring_config_from_context_defaults() -> None:
    config = scoring_config_from_context({"config": {}})
    assert config.enabled is True
    assert config.scorer_version == "v1"
    assert config.select_m == 40
    assert config.top_k == 10
    assert config.tie_breakers == ["score_total_desc", "published_desc", "paper_id_asc"]


def test_scoring_config_from_context_applies_overrides() -> None:
    config = scoring_config_from_context(
        {
            "config": {
                "scoring": {
                    "enabled": False,
                    "select_m": 12,
                    "top_k": 5,
                    "topic_alignment": {"keywords": [" llm ", "agents"]},
                    "weights": {"topic_alignment": 1.0, "recency": 0.0},
                }
            }
        }
    )
    assert config.enabled is False
    assert config.select_m == 12
    assert config.top_k == 5
    assert config.topic_alignment.keywords == ["llm", "agents"]
    assert config.weights.topic_alignment == 1.0
    assert config.weights.recency == 0.0


def test_scoring_config_from_context_rejects_non_mapping_values() -> None:
    with pytest.raises(TypeError, match="ctx\\['config'\\] must be a mapping"):
        scoring_config_from_context({"config": "invalid"})
    with pytest.raises(TypeError, match="ctx\\['config'\\]\\['scoring'\\] must be a mapping"):
        scoring_config_from_context({"config": {"scoring": "invalid"}})


def test_scoring_config_validates_selection_bounds() -> None:
    with pytest.raises(ValidationError, match="top_k must be <= select_m"):
        ScoringConfig(select_m=2, top_k=3)


def test_scoring_weights_validate_non_negative_and_positive_sum() -> None:
    with pytest.raises(ValidationError, match="weights must be non-negative"):
        ScoringWeights(topic_alignment=-0.1)
    with pytest.raises(ValidationError, match="weights sum must be > 0"):
        ScoringWeights(
            topic_alignment=0.0,
            recency=0.0,
            credibility=0.0,
            methodological_rigor=0.0,
            engagement=0.0,
        )


def test_paper_feature_scores_enforce_bounds() -> None:
    with pytest.raises(ValidationError):
        PaperFeatureScores(
            paper_id="1234.5678",
            topic_alignment=1.1,
            recency=0.5,
            credibility=0.5,
            methodological_rigor=0.5,
            engagement=0.5,
        )
