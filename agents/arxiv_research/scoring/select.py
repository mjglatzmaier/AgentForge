from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from agents.arxiv_research.scoring.models import ScoredPaper, ScoringConfig, ScoringDiagnostics

_SUPPORTED_TIE_BREAKERS = {"score_total_desc", "published_desc", "paper_id_asc"}


def order_scored_papers(
    scored_papers: list[ScoredPaper],
    *,
    tie_breakers: list[str],
) -> list[ScoredPaper]:
    _validate_tie_breakers(tie_breakers)
    ordered = sorted(scored_papers, key=_sort_key)
    ranked: list[ScoredPaper] = []
    for index, item in enumerate(ordered, start=1):
        ranked.append(item.model_copy(update={"rank": index}))
    return ranked


def select_scored_papers(
    *,
    scored_papers: list[ScoredPaper],
    config: ScoringConfig,
    diagnostics: ScoringDiagnostics,
) -> tuple[list[ScoredPaper], ScoringDiagnostics]:
    thresholded = [
        item for item in scored_papers if item.score_total >= float(config.min_score_threshold)
    ]
    selected_m = thresholded[: config.select_m]
    selected = selected_m[: config.top_k]

    updated = diagnostics.model_copy(
        update={
            "selected_count": len(selected),
            "dropped_below_threshold": len(scored_papers) - len(thresholded),
            "notes": [
                *diagnostics.notes,
                f"min_score_threshold={float(config.min_score_threshold):.3f}",
                f"select_m={config.select_m}",
                f"top_k={config.top_k}",
            ],
        }
    )
    return selected, updated


def build_scoring_payload(
    *,
    scored_papers: list[ScoredPaper],
    selected_papers: list[ScoredPaper],
    diagnostics: ScoringDiagnostics,
) -> dict[str, Any]:
    return {
        "papers_scored": [item.model_dump(mode="json") for item in scored_papers],
        "papers_selected": [item.model_dump(mode="json") for item in selected_papers],
        "scoring_diagnostics": diagnostics.model_dump(mode="json"),
    }


def _validate_tie_breakers(tie_breakers: list[str]) -> None:
    unsupported = [item for item in tie_breakers if item not in _SUPPORTED_TIE_BREAKERS]
    if unsupported:
        raise ValueError(f"Unsupported tie_breakers: {unsupported}")


def _sort_key(item: ScoredPaper) -> tuple[float, float, str]:
    published_ts = _published_timestamp_utc(item.paper.published)
    return (-item.score_total, -published_ts, item.paper.paper_id)


def _published_timestamp_utc(published: str) -> float:
    normalized = published.strip()
    if not normalized:
        return 0.0
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return 0.0
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).timestamp()
