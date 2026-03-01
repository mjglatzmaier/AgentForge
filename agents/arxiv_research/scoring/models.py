from __future__ import annotations

from typing import Any, Mapping

from pydantic import BaseModel, Field, field_validator, model_validator

from agents.arxiv_research.models import ResearchPaper

_DEFAULT_TIE_BREAKERS = ["score_total_desc", "published_desc", "paper_id_asc"]


def scoring_config_from_context(ctx: Mapping[str, Any]) -> "ScoringConfig":
    raw_config = ctx.get("config", {})
    if raw_config is None:
        raw_config = {}
    if not isinstance(raw_config, Mapping):
        raise TypeError("ctx['config'] must be a mapping when provided.")

    raw_scoring = raw_config.get("scoring", {})
    if raw_scoring is None:
        raw_scoring = {}
    if not isinstance(raw_scoring, Mapping):
        raise TypeError("ctx['config']['scoring'] must be a mapping when provided.")
    return ScoringConfig.model_validate(dict(raw_scoring))


def _normalize_string_list(values: list[str], *, field_name: str) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = value.strip()
        if not item:
            raise ValueError(f"{field_name} entries must be non-empty.")
        normalized.append(item)
    return normalized


class TopicAlignmentConfig(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    phrases: list[str] = Field(default_factory=list)
    title_weight: float = 2.0
    abstract_weight: float = 1.0
    category_bonus: float = 0.15

    @field_validator("keywords", "phrases")
    @classmethod
    def validate_terms(cls, values: list[str], info: Any) -> list[str]:
        return _normalize_string_list(values, field_name=str(info.field_name))


class RecencyConfig(BaseModel):
    half_life_days: int = 180

    @field_validator("half_life_days")
    @classmethod
    def validate_half_life_days(cls, value: int) -> int:
        if value < 1:
            raise ValueError("half_life_days must be >= 1.")
        return value


class CredibilityConfig(BaseModel):
    doi_bonus: float = 0.10
    journal_ref_bonus: float = 0.10


class MethodologicalRigorConfig(BaseModel):
    experiment_terms: list[str] = Field(default_factory=list)
    theory_terms: list[str] = Field(default_factory=list)

    @field_validator("experiment_terms", "theory_terms")
    @classmethod
    def validate_terms(cls, values: list[str], info: Any) -> list[str]:
        return _normalize_string_list(values, field_name=str(info.field_name))


class EngagementConfig(BaseModel):
    proxy_terms: list[str] = Field(default_factory=list)
    proxy_bonus_per_hit: float = 0.05
    max_proxy_bonus: float = 0.25

    @field_validator("proxy_terms")
    @classmethod
    def validate_terms(cls, values: list[str]) -> list[str]:
        return _normalize_string_list(values, field_name="proxy_terms")


class ScoringWeights(BaseModel):
    topic_alignment: float = 0.45
    recency: float = 0.20
    credibility: float = 0.10
    methodological_rigor: float = 0.15
    engagement: float = 0.10

    @model_validator(mode="after")
    def validate_weights(self) -> "ScoringWeights":
        values = {
            "topic_alignment": self.topic_alignment,
            "recency": self.recency,
            "credibility": self.credibility,
            "methodological_rigor": self.methodological_rigor,
            "engagement": self.engagement,
        }
        if any(value < 0 for value in values.values()):
            raise ValueError("weights must be non-negative.")
        if sum(values.values()) <= 0:
            raise ValueError("weights sum must be > 0.")
        return self


class EnrichmentConfig(BaseModel):
    enabled: bool = False
    source: str | None = None


class ScoringConfig(BaseModel):
    enabled: bool = True
    scorer_version: str = "v1"
    select_m: int = 40
    top_k: int = 10
    min_score_threshold: float = 0.0
    tie_breakers: list[str] = Field(default_factory=lambda: list(_DEFAULT_TIE_BREAKERS))
    topic_alignment: TopicAlignmentConfig = Field(default_factory=TopicAlignmentConfig)
    recency: RecencyConfig = Field(default_factory=RecencyConfig)
    credibility: CredibilityConfig = Field(default_factory=CredibilityConfig)
    methodological_rigor: MethodologicalRigorConfig = Field(
        default_factory=MethodologicalRigorConfig
    )
    engagement: EngagementConfig = Field(default_factory=EngagementConfig)
    weights: ScoringWeights = Field(default_factory=ScoringWeights)
    enrichment: EnrichmentConfig = Field(default_factory=EnrichmentConfig)

    @field_validator("scorer_version")
    @classmethod
    def validate_scorer_version(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("scorer_version must be non-empty.")
        return normalized

    @field_validator("select_m", "top_k")
    @classmethod
    def validate_positive_counts(cls, value: int, info: Any) -> int:
        if value < 1:
            raise ValueError(f"{info.field_name} must be >= 1.")
        return value

    @field_validator("tie_breakers")
    @classmethod
    def validate_tie_breakers(cls, values: list[str]) -> list[str]:
        return _normalize_string_list(values, field_name="tie_breakers")

    @model_validator(mode="after")
    def validate_selection_bounds(self) -> "ScoringConfig":
        if self.top_k > self.select_m:
            raise ValueError("top_k must be <= select_m.")
        return self


class PaperFeatureScores(BaseModel):
    paper_id: str
    topic_alignment: float = Field(ge=0.0, le=1.0)
    recency: float = Field(ge=0.0, le=1.0)
    credibility: float = Field(ge=0.0, le=1.0)
    methodological_rigor: float = Field(ge=0.0, le=1.0)
    engagement: float = Field(ge=0.0, le=1.0)
    factor_explanations: dict[str, str] = Field(default_factory=dict)

    @field_validator("paper_id")
    @classmethod
    def validate_paper_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("paper_id must be non-empty.")
        return normalized


class ScoredPaper(BaseModel):
    paper: ResearchPaper
    feature_scores: PaperFeatureScores
    score_total: float = Field(ge=0.0)
    rank: int | None = Field(default=None, ge=1)


class ScoringDiagnostics(BaseModel):
    scorer_version: str = "v1"
    weights_normalized: ScoringWeights = Field(default_factory=ScoringWeights)
    candidate_count: int = Field(ge=0)
    selected_count: int = Field(ge=0)
    dropped_below_threshold: int = Field(default=0, ge=0)
    notes: list[str] = Field(default_factory=list)
