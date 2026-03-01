from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.arxiv_research.models import ResearchPaper
from agents.arxiv_research.scoring.aggregate import aggregate_scored_papers
from agents.arxiv_research.scoring.enrichment import resolve_enrichment_adapter
from agents.arxiv_research.scoring.features import compute_feature_scores
from agents.arxiv_research.scoring.models import ScoringConfig, scoring_config_from_context
from agents.arxiv_research.scoring.select import (
    build_scoring_payload,
    order_scored_papers,
    select_scored_papers,
)


def score_papers(ctx: dict[str, Any]) -> dict[str, Any]:
    step_dir = Path(str(ctx["step_dir"]))
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    mode = _mode_from_context(ctx)
    config = scoring_config_from_context(ctx)
    papers = _read_papers_input(ctx, "papers_raw")
    enrichment_signals = _resolve_enrichment_signals(
        ctx=ctx,
        papers=papers,
        config=config,
        mode=mode,
    )
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
    diagnostics_payload = dict(payload["scoring_diagnostics"])
    diagnostics_payload["enrichment_enabled"] = config.enrichment.enabled
    diagnostics_payload["enrichment_source"] = config.enrichment.source
    diagnostics_payload["enrichment_signal_count"] = _enrichment_signal_count(
        enrichment_signals
    )
    if config.enrichment.enabled:
        diagnostics_payload.setdefault("notes", [])
        diagnostics_payload["notes"] = [
            *diagnostics_payload["notes"],
            f"enrichment_mode={mode}",
            f"enrichment_signals={diagnostics_payload['enrichment_signal_count']}",
        ]

    _write_json(outputs_dir / "papers_scored.json", payload["papers_scored"])
    _write_json(outputs_dir / "papers_selected.json", payload["papers_selected"])
    _write_json(outputs_dir / "scoring_diagnostics.json", diagnostics_payload)

    outputs: list[dict[str, str]] = [
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
    ]
    if config.enrichment.enabled:
        _write_json(outputs_dir / "scoring_enrichment_snapshot.json", enrichment_signals)
        outputs.append(
            {
                "name": "scoring_enrichment_snapshot",
                "type": "json",
                "path": "outputs/scoring_enrichment_snapshot.json",
            }
        )
    return {
        "outputs": outputs,
        "metrics": {
            "candidate_count": diagnostics.candidate_count,
            "selected_count": diagnostics.selected_count,
            "dropped_below_threshold": diagnostics.dropped_below_threshold,
            "enrichment_signal_count": _enrichment_signal_count(enrichment_signals),
        },
    }


def _mode_from_context(ctx: dict[str, Any]) -> str:
    config = ctx.get("config", {})
    if not isinstance(config, dict):
        raise TypeError("ctx['config'] must be a mapping when provided.")
    mode = str(config.get("mode", "live")).strip().lower()
    if mode not in {"live", "replay"}:
        raise ValueError(f"Unsupported score_papers mode: {mode}")
    return mode


def _resolve_enrichment_signals(
    *,
    ctx: dict[str, Any],
    papers: list[ResearchPaper],
    config: ScoringConfig,
    mode: str,
) -> dict[str, dict[str, str | int | float | bool | None]]:
    if not config.enrichment.enabled:
        return {}
    if mode == "replay":
        return _read_enrichment_snapshot_input(ctx, "scoring_enrichment_snapshot")
    adapter = resolve_enrichment_adapter(config)
    return adapter.fetch_signals(papers, config=config)


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


def _read_enrichment_snapshot_input(
    ctx: dict[str, Any], artifact_name: str
) -> dict[str, dict[str, str | int | float | bool | None]]:
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
    if not isinstance(payload, dict):
        raise TypeError(f"Input artifact '{artifact_name}' must contain a JSON object.")
    normalized: dict[str, dict[str, str | int | float | bool | None]] = {}
    for paper_id, signals in payload.items():
        if not isinstance(paper_id, str):
            raise TypeError(f"Input artifact '{artifact_name}' keys must be paper_id strings.")
        if not isinstance(signals, dict):
            raise TypeError(
                f"Input artifact '{artifact_name}' values must be signal objects keyed by paper_id."
            )
        normalized[paper_id] = dict(signals)
    return normalized


def _enrichment_signal_count(
    signals: dict[str, dict[str, str | int | float | bool | None]]
) -> int:
    return len(signals)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
