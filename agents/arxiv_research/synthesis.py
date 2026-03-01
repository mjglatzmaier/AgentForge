from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentforge.providers import (
    BaseProvider,
    ClaudeProvider,
    LlmResult,
    OpenAIProvider,
    ProviderValidationError,
)
from agents.arxiv_research.models import ResearchDigest, ResearchPaper

_SYSTEM_PROMPT = (
    "You are a research synthesis assistant. "
    "Return only strict JSON matching the response schema."
)
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_TIMEOUT_S = 60.0
_DEFAULT_MAX_OUTPUT_TOKENS = 2000


def synthesize_digest(ctx: dict[str, Any]) -> dict[str, Any]:
    papers = _load_synthesis_papers(ctx)
    prompt = _build_synthesis_prompt(papers)
    settings = _synthesis_settings(ctx)
    provider = _resolve_provider(ctx)

    result: LlmResult[ResearchDigest] = provider.generate_json(
        prompt=prompt,
        response_model=ResearchDigest,
        system_prompt=_SYSTEM_PROMPT,
        model=settings["model"],
        temperature=settings["temperature"],
        max_output_tokens=settings["max_output_tokens"],
        seed=settings["seed"],
        timeout_s=settings["timeout_s"],
        metadata={
            "run_id": str(ctx.get("run_id", "")),
            "step_id": str(ctx.get("step_id", "synthesize_digest")),
            "mode": settings["mode"],
        },
    )

    digest = result.parsed
    _validate_citations(digest=digest, papers=papers)

    step_dir = Path(ctx["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    (outputs_dir / "digest.json").write_text(
        json.dumps(digest.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    return {
        "outputs": [{"name": "digest_json", "type": "json", "path": "outputs/digest.json"}],
        "metrics": {
            "papers": len(papers),
            "highlights": len(digest.highlights),
            "mode": settings["mode"],
        },
    }


def _build_synthesis_prompt(papers: list[ResearchPaper]) -> str:
    ordered = sorted(papers, key=lambda paper: (paper.published, paper.paper_id))
    papers_payload = [paper.model_dump(mode="json") for paper in ordered]
    papers_json = json.dumps(papers_payload, sort_keys=True, indent=2)
    return (
        "Summarize key contributions from the provided papers.\n"
        "Produce max of 5 concise bullet highlights for the most important findings. Max 100 words per highlight, use clear, high-level language.\n"
        "Every highlight MUST include cited_paper_ids with one or more paper_id values from the input.\n"
        "Input papers JSON:\n"
        f"{papers_json}"
    )


def _synthesis_settings(ctx: dict[str, Any]) -> dict[str, str | float | int | None]:
    config = dict(ctx.get("config", {}))
    mode = str(config.get("mode", "live")).strip().lower()
    if mode not in {"live", "replay"}:
        raise ValueError(f"Unsupported synthesis mode: {mode}")

    model = str(config.get("model", _DEFAULT_MODEL))
    timeout_s = float(config.get("timeout_s", _DEFAULT_TIMEOUT_S))
    max_output_tokens = int(config.get("max_output_tokens", _DEFAULT_MAX_OUTPUT_TOKENS))
    raw_seed = config.get("seed")

    if mode == "replay":
        seed = int(raw_seed) if raw_seed is not None else 0
        temperature = 0.0
    else:
        seed = int(raw_seed) if raw_seed is not None else None
        temperature = float(config.get("temperature", 0.2))

    return {
        "mode": mode,
        "model": model,
        "timeout_s": timeout_s,
        "max_output_tokens": max_output_tokens,
        "seed": seed,
        "temperature": temperature,
    }


def _resolve_provider(ctx: dict[str, Any]) -> BaseProvider:
    provider_name = str(ctx.get("config", {}).get("provider", "openai")).strip().lower()
    if provider_name == "openai":
        return OpenAIProvider()
    if provider_name == "claude":
        return ClaudeProvider()
    raise ValueError(f"Unsupported provider: {provider_name}")


def _load_papers_input(ctx: dict[str, Any], artifact_name: str) -> list[ResearchPaper]:
    artifact = _require_input_artifact(ctx, artifact_name)
    payload = json.loads(Path(artifact["abs_path"]).read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError(f"Input artifact '{artifact_name}' must contain a JSON list.")
    normalized_payload: list[dict[str, Any]] = []
    for item in payload:
        if isinstance(item, dict) and isinstance(item.get("paper"), dict):
            normalized_payload.append(dict(item["paper"]))
        else:
            normalized_payload.append(item)
    return [ResearchPaper.model_validate(item) for item in normalized_payload]


def _load_synthesis_papers(ctx: dict[str, Any]) -> list[ResearchPaper]:
    inputs = ctx.get("inputs", {})
    if isinstance(inputs, dict) and "papers_selected" in inputs:
        return _load_papers_input(ctx, "papers_selected")
    if isinstance(inputs, dict) and "papers_raw" in inputs:
        return _load_papers_input(ctx, "papers_raw")
    raise KeyError("Missing required input artifact: papers_selected or papers_raw")


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


def _validate_citations(*, digest: ResearchDigest, papers: list[ResearchPaper]) -> None:
    valid_paper_ids = {paper.paper_id for paper in papers}
    invalid_entries: list[str] = []

    for index, highlight in enumerate(digest.highlights):
        if not highlight.cited_paper_ids:
            invalid_entries.append(f"highlight[{index}] has no cited_paper_ids")
            continue
        invalid_ids = sorted({paper_id for paper_id in highlight.cited_paper_ids if paper_id not in valid_paper_ids})
        if invalid_ids:
            invalid_entries.append(
                f"highlight[{index}] includes unknown cited_paper_ids: {invalid_ids}"
            )

    if invalid_entries:
        raise ProviderValidationError("Invalid highlight citations: " + "; ".join(invalid_entries))
