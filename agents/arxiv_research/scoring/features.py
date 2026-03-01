from __future__ import annotations

from datetime import datetime, timezone

from agents.arxiv_research.models import ResearchPaper
from agents.arxiv_research.scoring.models import PaperFeatureScores, ScoringConfig

_CREDIBILITY_JOURNAL_MARKERS = (
    "journal",
    "transactions",
    "proceedings",
    "conference",
)


def compute_feature_scores(
    papers: list[ResearchPaper],
    config: ScoringConfig,
    *,
    now_utc: datetime | None = None,
) -> list[PaperFeatureScores]:
    return [
        compute_feature_scores_for_paper(paper, config, now_utc=now_utc)
        for paper in papers
    ]


def compute_feature_scores_for_paper(
    paper: ResearchPaper,
    config: ScoringConfig,
    *,
    now_utc: datetime | None = None,
) -> PaperFeatureScores:
    topic_alignment, topic_expl = _topic_alignment_score(paper, config)
    recency, recency_expl = _recency_score(paper, config, now_utc=now_utc)
    credibility, credibility_expl = _credibility_score(paper, config)
    rigor, rigor_expl = _methodological_rigor_score(paper, config)
    engagement, engagement_expl = _engagement_score(paper, config)
    return PaperFeatureScores(
        paper_id=paper.paper_id,
        topic_alignment=topic_alignment,
        recency=recency,
        credibility=credibility,
        methodological_rigor=rigor,
        engagement=engagement,
        factor_explanations={
            "topic_alignment": topic_expl,
            "recency": recency_expl,
            "credibility": credibility_expl,
            "methodological_rigor": rigor_expl,
            "engagement": engagement_expl,
        },
    )


def _topic_alignment_score(paper: ResearchPaper, config: ScoringConfig) -> tuple[float, str]:
    keywords = _normalized_unique(config.topic_alignment.keywords)
    phrases = _normalized_unique(config.topic_alignment.phrases)
    title = _normalize_text(paper.title)
    abstract = _normalize_text(paper.abstract)
    categories_text = " ".join(_normalize_text(category) for category in paper.categories)

    title_hits = _count_present_terms(title, [*keywords, *phrases])
    abstract_hits = _count_present_terms(abstract, [*keywords, *phrases])
    category_match = bool(_count_present_terms(categories_text, [*keywords, *phrases]))

    title_weight = max(config.topic_alignment.title_weight, 0.0)
    abstract_weight = max(config.topic_alignment.abstract_weight, 0.0)
    category_bonus = max(config.topic_alignment.category_bonus, 0.0)

    max_weighted_hits = (title_weight + abstract_weight) * float(len(keywords) + len(phrases))
    weighted_hits = (title_weight * title_hits) + (abstract_weight * abstract_hits)
    if max_weighted_hits <= 0.0:
        base_score = 0.0
    else:
        base_score = weighted_hits / max_weighted_hits
    if category_match and category_bonus > 0.0:
        base_score += category_bonus
    score = _clamp_01(base_score)
    explanation = (
        f"title_hits={title_hits}, abstract_hits={abstract_hits}, "
        f"category_match={category_match}, score={score:.3f}"
    )
    return score, explanation


def _recency_score(
    paper: ResearchPaper,
    config: ScoringConfig,
    *,
    now_utc: datetime | None = None,
) -> tuple[float, str]:
    published = _parse_published_utc(paper.published)
    if published is None:
        return 0.0, "published parse failed, score=0.000"

    now = now_utc or datetime.now(timezone.utc)
    now = now.astimezone(timezone.utc)
    age_days = max(0.0, (now - published).total_seconds() / 86_400.0)
    half_life_days = float(max(config.recency.half_life_days, 1))
    score = _clamp_01(0.5 ** (age_days / half_life_days))
    return score, f"age_days={age_days:.1f}, half_life_days={half_life_days:.0f}, score={score:.3f}"


def _credibility_score(paper: ResearchPaper, config: ScoringConfig) -> tuple[float, str]:
    text = f"{paper.title} {paper.abstract}".lower()
    has_doi = "doi:" in text or "doi.org/" in text
    has_journal_ref = any(marker in text for marker in _CREDIBILITY_JOURNAL_MARKERS)

    doi_bonus = max(config.credibility.doi_bonus, 0.0)
    journal_bonus = max(config.credibility.journal_ref_bonus, 0.0)
    max_bonus = doi_bonus + journal_bonus
    awarded = (doi_bonus if has_doi else 0.0) + (journal_bonus if has_journal_ref else 0.0)
    if max_bonus <= 0.0:
        score = 0.0
    else:
        score = _clamp_01(awarded / max_bonus)
    return score, f"has_doi={has_doi}, has_journal_ref={has_journal_ref}, score={score:.3f}"


def _methodological_rigor_score(
    paper: ResearchPaper, config: ScoringConfig
) -> tuple[float, str]:
    text = _normalize_text(f"{paper.title} {paper.abstract}")
    experiment_terms = _normalized_unique(config.methodological_rigor.experiment_terms)
    theory_terms = _normalized_unique(config.methodological_rigor.theory_terms)

    components: list[float] = []
    experiment_hits = _count_present_terms(text, experiment_terms)
    if experiment_terms:
        components.append(experiment_hits / float(len(experiment_terms)))

    theory_hits = _count_present_terms(text, theory_terms)
    if theory_terms:
        components.append(theory_hits / float(len(theory_terms)))

    if not components:
        score = 0.0
    else:
        score = _clamp_01(sum(components) / float(len(components)))
    return (
        score,
        f"experiment_hits={experiment_hits}, theory_hits={theory_hits}, score={score:.3f}",
    )


def _engagement_score(paper: ResearchPaper, config: ScoringConfig) -> tuple[float, str]:
    text = _normalize_text(f"{paper.title} {paper.abstract}")
    proxy_terms = _normalized_unique(config.engagement.proxy_terms)
    hits = _count_present_terms(text, proxy_terms)
    per_hit = max(config.engagement.proxy_bonus_per_hit, 0.0)
    max_bonus = max(config.engagement.max_proxy_bonus, 0.0)
    raw_bonus = float(hits) * per_hit
    if max_bonus <= 0.0:
        score = 0.0
    else:
        score = _clamp_01(min(raw_bonus, max_bonus) / max_bonus)
    return score, f"proxy_hits={hits}, raw_bonus={raw_bonus:.3f}, score={score:.3f}"


def _count_present_terms(text: str, terms: list[str]) -> int:
    return sum(1 for term in terms if term and term in text)


def _normalized_unique(values: list[str]) -> list[str]:
    seen: dict[str, None] = {}
    for value in values:
        normalized = _normalize_text(value)
        if normalized and normalized not in seen:
            seen[normalized] = None
    return list(seen.keys())


def _normalize_text(value: str) -> str:
    return " ".join(value.lower().split())


def _parse_published_utc(value: str) -> datetime | None:
    normalized = value.strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _clamp_01(value: float) -> float:
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value
