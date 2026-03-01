from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.arxiv_research.models import ResearchDigest


def render_report(ctx: dict[str, Any]) -> dict[str, Any]:
    digest = _load_digest_input(ctx, "digest_json")
    _validate_highlight_citations(digest)

    step_dir = Path(ctx["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    digest_path = outputs_dir / "digest.json"
    report_path = outputs_dir / "report.md"
    sources_path = outputs_dir / "sources.json"

    digest_path.write_text(json.dumps(digest.model_dump(mode="json"), indent=2), encoding="utf-8")
    report_path.write_text(_render_markdown_report(digest), encoding="utf-8")
    sources_path.write_text(
        json.dumps([paper.model_dump(mode="json") for paper in digest.papers], indent=2),
        encoding="utf-8",
    )

    return {
        "outputs": [
            {"name": "digest_json", "type": "json", "path": "outputs/digest.json"},
            {"name": "report_md", "type": "markdown", "path": "outputs/report.md"},
            {"name": "sources_json", "type": "json", "path": "outputs/sources.json"},
        ],
        "metrics": {"papers": len(digest.papers), "highlights": len(digest.highlights)},
    }


def _load_digest_input(ctx: dict[str, Any], artifact_name: str) -> ResearchDigest:
    artifact = _require_input_artifact(ctx, artifact_name)
    payload = json.loads(Path(artifact["abs_path"]).read_text(encoding="utf-8"))
    return ResearchDigest.model_validate(payload)


def _require_input_artifact(ctx: dict[str, Any], artifact_name: str) -> dict[str, Any]:
    inputs = ctx.get("inputs", {})
    artifact = inputs.get(artifact_name)
    if artifact is None:
        raise KeyError(f"Missing required input artifact: {artifact_name}")
    if not isinstance(artifact, dict):
        raise TypeError(f"Input artifact '{artifact_name}' must be a metadata dict.")
    abs_path = artifact.get("abs_path")
    if not isinstance(abs_path, str) or not abs_path:
        raise TypeError(f"Input artifact '{artifact_name}' must include non-empty 'abs_path'.")
    return dict(artifact)


def _validate_highlight_citations(digest: ResearchDigest) -> None:
    valid_paper_ids = {paper.paper_id for paper in digest.papers}
    invalid: list[str] = []
    for index, highlight in enumerate(digest.highlights):
        unknown = sorted({paper_id for paper_id in highlight.cited_paper_ids if paper_id not in valid_paper_ids})
        if unknown:
            invalid.append(f"highlight[{index}] references unknown paper_id(s): {unknown}")
    if invalid:
        raise ValueError("; ".join(invalid))


def _render_markdown_report(digest: ResearchDigest) -> str:
    # Build lookup: paper_id -> list of highlight texts
    highlights_by_paper: dict[str, list[str]] = {}

    for highlight in digest.highlights or []:
        for paper_id in highlight.cited_paper_ids:
            highlights_by_paper.setdefault(paper_id, []).append(highlight.text)

    lines = [
        "# ArXiv Research Report",
        "",
        f"Query: `{digest.query}`",
        f"Generated: `{digest.generated_at_utc.isoformat()}`",
        "",
        "## Papers",
        "",
        "| paper_id | title | published | categories | highlights |",
        "| --- | --- | --- | --- | --- |",
    ]

    for paper in digest.papers:
        categories = ", ".join(paper.categories)

        paper_highlights = highlights_by_paper.get(paper.paper_id, [])
        if paper_highlights:
            formatted_highlights = "<br>".join(
                f"- {text}" for text in paper_highlights
            )
        else:
            formatted_highlights = "—"

        lines.append(
            f"| `{paper.paper_id}` | {paper.title} | {paper.published} | "
            f"{categories} | {formatted_highlights} |"
        )

    lines.extend(["", "## Highlights", ""])
    for highlight in digest.highlights:
        cited = ", ".join(f"`{paper_id}`" for paper_id in highlight.cited_paper_ids)
        lines.append(f"- {highlight.text} ({cited})")

    return "\n".join(lines) + "\n"
