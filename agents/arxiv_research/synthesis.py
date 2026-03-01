from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from agentforge.providers import (
    BaseProvider,
    ClaudeProvider,
    LlmResult,
    OpenAIProvider,
    ProviderValidationError,
)
from agents.arxiv_research.models import ResearchDigest, ResearchPaper, SynthesisHighlights

_SYSTEM_PROMPT = (
    "You are a research synthesis assistant. "
    "Return only strict JSON matching the response schema."
)
_DEFAULT_MODEL = "gpt-4o-mini"
_DEFAULT_TIMEOUT_S = 60.0
_DEFAULT_MAX_OUTPUT_TOKENS = 2000
_FINISH_REASON_RE = re.compile(r"finish_reason=([A-Za-z0-9_-]+|None|null)")


def synthesize_digest(ctx: dict[str, Any]) -> dict[str, Any]:
    papers = _load_synthesis_papers(ctx)
    prompt = _build_synthesis_prompt(papers)
    settings = _synthesis_settings(ctx)
    provider = _resolve_provider(ctx)
    step_dir = Path(ctx["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    diagnostics = _base_synthesis_diagnostics(
        mode=str(settings["mode"]),
        provider_name=str(getattr(provider, "name", "unknown")),
        model=str(settings["model"]),
        prompt=prompt,
    )

    try:
        result: LlmResult[SynthesisHighlights] = provider.generate_json(
            prompt=prompt,
            response_model=SynthesisHighlights,
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

        digest = _build_research_digest(
            highlights_payload=result.parsed,
            papers=papers,
            ctx=ctx,
            mode=str(settings["mode"]),
        )
        _validate_citations(digest=digest, papers=papers)
    except ProviderValidationError as exc:
        _record_failure_diagnostics(diagnostics=diagnostics, error_text=str(exc))
        _write_json(outputs_dir / "synthesis_diagnostics.json", diagnostics)
        raise

    diagnostics["status"] = "success"
    diagnostics["provider"] = result.provider
    diagnostics["model"] = result.model
    diagnostics["latency_ms"] = result.latency_ms
    diagnostics["usage"] = dict(result.usage)
    (outputs_dir / "digest.json").write_text(
        json.dumps(digest.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )
    _write_json(outputs_dir / "synthesis_diagnostics.json", diagnostics)

    return {
        "outputs": [
            {"name": "digest_json", "type": "json", "path": "outputs/digest.json"},
            {
                "name": "synthesis_diagnostics",
                "type": "json",
                "path": "outputs/synthesis_diagnostics.json",
            },
        ],
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


def _build_research_digest(
    *,
    highlights_payload: SynthesisHighlights,
    papers: list[ResearchPaper],
    ctx: dict[str, Any],
    mode: str,
) -> ResearchDigest:
    return ResearchDigest(
        query=_resolve_digest_query(highlights_payload=highlights_payload, ctx=ctx),
        generated_at_utc=_resolve_generated_at_utc(ctx=ctx, papers=papers, mode=mode),
        papers=[paper.model_copy(deep=True) for paper in papers],
        highlights=[highlight.model_copy(deep=True) for highlight in highlights_payload.highlights],
    )


def _resolve_digest_query(*, highlights_payload: SynthesisHighlights, ctx: dict[str, Any]) -> str:
    if highlights_payload.query is not None:
        return highlights_payload.query
    config = ctx.get("config", {})
    if isinstance(config, dict):
        raw_query = config.get("query")
        if isinstance(raw_query, str) and raw_query.strip():
            return raw_query.strip()
    return "research digest"


def _resolve_generated_at_utc(
    *,
    ctx: dict[str, Any],
    papers: list[ResearchPaper],
    mode: str,
) -> datetime:
    config = ctx.get("config", {})
    if isinstance(config, dict):
        raw_generated_at = config.get("generated_at_utc")
        if isinstance(raw_generated_at, str) and raw_generated_at.strip():
            try:
                return _parse_aware_datetime(raw_generated_at)
            except ValueError as exc:
                raise ValueError("config.generated_at_utc must be ISO-8601 when provided.") from exc
    if mode == "replay":
        return _deterministic_replay_timestamp(papers)
    return datetime.now(timezone.utc)


def _deterministic_replay_timestamp(papers: list[ResearchPaper]) -> datetime:
    timestamps: list[datetime] = []
    for paper in papers:
        try:
            timestamps.append(_parse_aware_datetime(paper.published))
        except ValueError:
            continue
    if timestamps:
        return max(timestamps) + timedelta(days=1)
    return datetime(1970, 1, 1, tzinfo=timezone.utc)


def _parse_aware_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _base_synthesis_diagnostics(
    *,
    mode: str,
    provider_name: str,
    model: str,
    prompt: str,
) -> dict[str, Any]:
    prompt_chars = len(prompt)
    return {
        "status": "pending",
        "mode": mode,
        "provider": provider_name,
        "model": model,
        "prompt_chars": prompt_chars,
        "est_prompt_tokens": _estimate_tokens_from_chars(prompt_chars),
        "retry_count": 0,
        "finish_reason": None,
        "overflow_detected": False,
        "error": None,
    }


def _record_failure_diagnostics(*, diagnostics: dict[str, Any], error_text: str) -> None:
    finish_reason = _extract_finish_reason(error_text)
    diagnostics["status"] = "failed"
    diagnostics["finish_reason"] = finish_reason
    diagnostics["overflow_detected"] = _is_overflow_error(error_text=error_text, finish_reason=finish_reason)
    diagnostics["error"] = error_text


def _extract_finish_reason(error_text: str) -> str | None:
    match = _FINISH_REASON_RE.search(error_text)
    if match is None:
        return None
    value = match.group(1).strip().strip(".")
    if value.lower() in {"none", "null"}:
        return None
    return value


def _is_overflow_error(*, error_text: str, finish_reason: str | None) -> bool:
    if finish_reason == "length":
        return True
    lowered = error_text.lower()
    return "truncat" in lowered or "max_tokens" in lowered


def _estimate_tokens_from_chars(char_count: int) -> int:
    return (char_count + 3) // 4


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
