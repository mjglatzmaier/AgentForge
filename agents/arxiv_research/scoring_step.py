from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.arxiv_research.models import ResearchPaper
from agents.arxiv_research.scoring.aggregate import aggregate_scored_papers
from agents.arxiv_research.scoring.features import compute_feature_scores
from agents.arxiv_research.scoring.models import scoring_config_from_context
from agents.arxiv_research.scoring.select import (
    build_scoring_payload,
    order_scored_papers,
    select_scored_papers,
)


def score_papers(ctx: dict[str, Any]) -> dict[str, Any]:
    step_dir = Path(str(ctx["step_dir"]))
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    config = scoring_config_from_context(ctx)
    papers = _read_papers_input(ctx, "papers_raw")
    feature_scores = compute_feature_scores(papers, config)
    scored, diagnostics = aggregate_scored_papers(
        papers=papers,
        feature_scores=feature_scores,
        config=config,
    )
    ordered = order_scored_papers(scored, tie_breakers=config.tie_breakers)
    selected, diagnostics = select_scored_papers(
        scored_papers=ordered,
        config=config,
        diagnostics=diagnostics,
    )
    payload = build_scoring_payload(
        scored_papers=ordered,
        selected_papers=selected,
        diagnostics=diagnostics,
    )

    _write_json(outputs_dir / "papers_scored.json", payload["papers_scored"])
    _write_json(outputs_dir / "papers_selected.json", payload["papers_selected"])
    _write_json(outputs_dir / "scoring_diagnostics.json", payload["scoring_diagnostics"])

    return {
        "outputs": [
            {"name": "papers_scored", "type": "json", "path": "outputs/papers_scored.json"},
            {
                "name": "papers_selected",
                "type": "json",
                "path": "outputs/papers_selected.json",
            },
            {
                "name": "scoring_diagnostics",
                "type": "json",
                "path": "outputs/scoring_diagnostics.json",
            },
        ],
        "metrics": {
            "candidate_count": diagnostics.candidate_count,
            "selected_count": diagnostics.selected_count,
            "dropped_below_threshold": diagnostics.dropped_below_threshold,
        },
    }


def _read_papers_input(ctx: dict[str, Any], artifact_name: str) -> list[ResearchPaper]:
    inputs = ctx.get("inputs", {})
    if not isinstance(inputs, dict):
        raise TypeError("ctx['inputs'] must be a mapping.")
    artifact = inputs.get(artifact_name)
    if not isinstance(artifact, dict):
        raise KeyError(f"Missing required input artifact '{artifact_name}'.")
    abs_path = artifact.get("abs_path")
    if not isinstance(abs_path, str) or not abs_path.strip():
        raise TypeError(f"Input artifact '{artifact_name}' must include non-empty 'abs_path'.")

    payload = json.loads(Path(abs_path).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError(f"Input artifact '{artifact_name}' must contain a JSON list.")
    return [ResearchPaper.model_validate(item) for item in payload]


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
