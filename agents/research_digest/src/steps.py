from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agentforge.providers import ClaudeProvider, OpenAIProvider, ProviderValidationError
from agents.research_digest.tools import arxiv as arxiv_tool
from agents.research_digest.tools import dedupe_rank as dedupe_rank_tool
from agents.research_digest.tools import normalize as normalize_tool
from agents.research_digest.tools import render as render_tool
from agents.research_digest.tools import rss as rss_tool
from agents.research_digest.tools.models import Digest, DigestItem, Doc


def fetch_arxiv(ctx: dict[str, Any]) -> dict[str, Any]:
    tool_ctx = _with_config(ctx, {"max_results": _max_docs(ctx)})
    arxiv_tool.fetch(tool_ctx)

    step_dir = Path(ctx["step_dir"])
    records = _read_records(step_dir / "outputs" / "arxiv_docs.json")
    records = _sort_records(records)
    records = _truncate(records, ctx)
    _write_records(step_dir / "outputs" / "docs_arxiv.json", records)

    return {
        "outputs": [{"name": "docs_arxiv", "type": "json", "path": "outputs/docs_arxiv.json"}],
        "metrics": {"count": len(records)},
    }


def fetch_rss(ctx: dict[str, Any]) -> dict[str, Any]:
    rss_tool.fetch(ctx)

    step_dir = Path(ctx["step_dir"])
    records = _read_records(step_dir / "outputs" / "rss_docs.json")
    records = _sort_records(records)
    records = _truncate(records, ctx)
    _write_records(step_dir / "outputs" / "docs_rss.json", records)

    return {
        "outputs": [{"name": "docs_rss", "type": "json", "path": "outputs/docs_rss.json"}],
        "metrics": {"count": len(records)},
    }


def normalize(ctx: dict[str, Any]) -> dict[str, Any]:
    normalize_inputs = {
        "arxiv_docs": _require_input(ctx, "docs_arxiv", "arxiv_docs"),
        "rss_docs": _require_input(ctx, "docs_rss", "rss_docs"),
    }
    tool_ctx = dict(ctx)
    tool_ctx["inputs"] = normalize_inputs
    normalize_tool.run(tool_ctx)

    step_dir = Path(ctx["step_dir"])
    records = _read_records(step_dir / "outputs" / "docs_norm.json")
    records = _sort_records(records)
    records = _truncate(records, ctx)
    _write_records(step_dir / "outputs" / "docs_normalized.json", records)

    return {
        "outputs": [{"name": "docs_normalized", "type": "json", "path": "outputs/docs_normalized.json"}],
        "metrics": {"count": len(records)},
    }


def dedupe_rank(ctx: dict[str, Any]) -> dict[str, Any]:
    dedupe_inputs = {"docs_norm": _require_input(ctx, "docs_normalized", "docs_norm")}
    tool_ctx = dict(ctx)
    tool_ctx["inputs"] = dedupe_inputs
    dedupe_rank_tool.run(tool_ctx)
    step_dir = Path(ctx["step_dir"])
    records = _read_records(step_dir / "outputs" / "docs_ranked.json")
    return {
        "outputs": [{"name": "docs_ranked", "type": "json", "path": "outputs/docs_ranked.json"}],
        "metrics": {"count": len(records)},
    }


def render(ctx: dict[str, Any]) -> dict[str, Any]:
    step_dir = Path(ctx["step_dir"])
    digest_input = ctx.get("inputs", {}).get("digest_json")
    if isinstance(digest_input, dict):
        digest_path = Path(_require_input(ctx, "digest_json")["abs_path"])
        digest = Digest.model_validate(json.loads(digest_path.read_text(encoding="utf-8")))
        outputs_dir = step_dir / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        (outputs_dir / "digest.md").write_text(_digest_to_markdown(digest), encoding="utf-8")
        return {
            "outputs": [{"name": "digest_md", "type": "markdown", "path": "outputs/digest.md"}],
            "metrics": {"count": len(digest.items)},
        }

    tool_ctx = dict(ctx)
    tool_ctx["inputs"] = {"docs_ranked": _require_input(ctx, "docs_ranked")}
    render_tool.run(tool_ctx)
    digest = json.loads((step_dir / "outputs" / "digest.json").read_text(encoding="utf-8"))
    return {
        "outputs": [
            {"name": "digest_json", "type": "json", "path": "outputs/digest.json"},
            {"name": "digest_md", "type": "markdown", "path": "outputs/digest.md"},
        ],
        "metrics": {"count": len(digest.get("items", []))},
    }


def synthesize_digest(ctx: dict[str, Any]) -> dict[str, Any]:
    docs_path = Path(_require_input(ctx, "docs_ranked", "docs_normalized")["abs_path"])
    docs = [Doc.model_validate(item) for item in json.loads(docs_path.read_text(encoding="utf-8"))]
    top_k = int(ctx.get("config", {}).get("top_k", 10))
    selected_docs = docs[:top_k] if top_k >= 0 else docs
    valid_doc_ids = {doc.doc_id for doc in selected_docs}

    prompt = _build_synthesis_prompt(selected_docs)
    provider = _resolve_provider(ctx)
    result = provider.generate_json(
        prompt=prompt,
        response_model=Digest,
        system_prompt=(
            "You are a research summarization assistant. "
            "Return only strict JSON. Every digest item must include non-empty citations."
        ),
        model=ctx.get("config", {}).get("model"),
        temperature=ctx.get("config", {}).get("temperature"),
        max_output_tokens=ctx.get("config", {}).get("max_output_tokens"),
        seed=ctx.get("config", {}).get("seed"),
        timeout_s=ctx.get("config", {}).get("timeout_s"),
        metadata={"run_id": ctx.get("run_id", ""), "step_id": ctx.get("step_id", "synthesize_digest")},
    )

    digest = _coerce_digest(result.parsed)
    _validate_digest_citations(digest, valid_doc_ids)

    step_dir = Path(ctx["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    (outputs_dir / "digest.json").write_text(
        json.dumps(digest.model_dump(mode="json"), indent=2),
        encoding="utf-8",
    )

    if ctx.get("mode") == "debug":
        (outputs_dir / "synthesis_prompt.txt").write_text(prompt, encoding="utf-8")
        (outputs_dir / "raw_response.txt").write_text(result.raw_text, encoding="utf-8")

    return {
        "outputs": [{"name": "digest_json", "type": "json", "path": "outputs/digest.json"}],
        "metrics": {"count": len(digest.items), "cited_items": len(digest.items)},
    }


def verify_digest_citations(ctx: dict[str, Any]) -> dict[str, Any]:
    digest_path = Path(_require_input(ctx, "digest_json")["abs_path"])
    docs_path = Path(_require_input(ctx, "docs_ranked", "docs_normalized")["abs_path"])
    digest = Digest.model_validate(json.loads(digest_path.read_text(encoding="utf-8")))
    docs = [Doc.model_validate(item) for item in json.loads(docs_path.read_text(encoding="utf-8"))]
    valid_doc_ids = {doc.doc_id for doc in docs}

    missing_citations = 0
    invalid_citation_entries: list[dict[str, Any]] = []
    for item in digest.items:
        citations = list(item.citations)
        if not citations:
            missing_citations += 1
        invalid = [citation for citation in citations if citation not in valid_doc_ids]
        if invalid:
            invalid_citation_entries.append(
                {"doc_id": item.doc_id, "invalid_citations": sorted(set(invalid))}
            )

    report = {
        "total_bullets": len(digest.items),
        "bullets_missing_citations": missing_citations,
        "invalid_doc_id_citations": invalid_citation_entries,
        "pass": missing_citations == 0 and len(invalid_citation_entries) == 0,
    }

    step_dir = Path(ctx["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    (outputs_dir / "citation_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    return {
        "outputs": [{"name": "citation_report", "type": "json", "path": "outputs/citation_report.json"}],
        "metrics": {
            "total_bullets": report["total_bullets"],
            "bullets_missing_citations": report["bullets_missing_citations"],
            "invalid_doc_id_citations": len(invalid_citation_entries),
            "pass": "true" if report["pass"] else "false",
        },
    }


def _with_config(ctx: dict[str, Any], updates: dict[str, int | None]) -> dict[str, Any]:
    merged_config = dict(ctx.get("config", {}))
    for key, value in updates.items():
        if value is not None:
            merged_config[key] = value
    tool_ctx = dict(ctx)
    tool_ctx["config"] = merged_config
    return tool_ctx


def _max_docs(ctx: dict[str, Any]) -> int | None:
    config = ctx.get("config", {})
    raw_value = config.get("max_docs")
    if raw_value is None:
        return None
    return int(raw_value)


def _truncate(records: list[dict[str, Any]], ctx: dict[str, Any]) -> list[dict[str, Any]]:
    max_docs = _max_docs(ctx)
    if max_docs is None or max_docs < 0:
        return records
    return records[:max_docs]


def _sort_records(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(records, key=lambda item: (str(item.get("published", "")), str(item.get("url", ""))))


def _read_records(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, list):
        raise TypeError(f"Expected list payload at {path}")
    return [dict(item) for item in payload]


def _write_records(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(records, indent=2), encoding="utf-8")


def _require_input(ctx: dict[str, Any], primary: str, legacy: str | None = None) -> dict[str, Any]:
    inputs = ctx.get("inputs", {})
    candidates = [primary]
    if legacy is not None:
        candidates.append(legacy)

    for name in candidates:
        entry = inputs.get(name)
        if entry is None:
            continue
        if not isinstance(entry, dict):
            raise TypeError(f"Input '{name}' must be a metadata dict.")
        abs_path = entry.get("abs_path")
        if not isinstance(abs_path, str) or not abs_path:
            raise TypeError(f"Input '{name}' must include non-empty 'abs_path'.")
        return dict(entry)

    raise KeyError(f"Missing required input artifact: {primary}")


def _resolve_provider(ctx: dict[str, Any]) -> OpenAIProvider | ClaudeProvider:
    provider_name = str(ctx.get("config", {}).get("provider", "openai")).lower()
    if provider_name == "openai":
        return OpenAIProvider()
    if provider_name == "claude":
        return ClaudeProvider()
    raise ValueError(f"Unsupported provider: {provider_name}")


def _build_synthesis_prompt(docs: list[Doc]) -> str:
    lines = [
        "Produce a JSON digest.",
        "Rules:",
        "- Every item must include citations with at least one doc_id.",
        "- Use only provided doc_ids for citations.",
        "- Do not hallucinate any information not supported by the cited documents.",
        "- Max words per bullet: 100. Focus on concise insights and simple language (high level for non-experts).",
        "- No newlines in any string values.",
        "Documents:",
    ]
    for doc in docs:
        lines.append(
            f"- doc_id={doc.doc_id} | title={doc.title} | source={doc.source} | "
            f"published={doc.published or ''} | url={doc.url} | summary={doc.summary}"
        )
    return "\n".join(lines)


def _digest_to_markdown(digest: Digest) -> str:
    lines = [f"# {digest.title}", "", f"Generated: {digest.generated_at}", ""]
    if not digest.items:
        lines.append("- No items found.")
        return "\n".join(lines) + "\n"

    for idx, item in enumerate(digest.items, start=1):
        lines.append(f"{idx}. **{item.title}** ({item.source}, score={item.score:.1f})")
        lines.append(f"   - doc_id: `{item.doc_id}`")
        lines.append(f"   - {item.summary}")
        lines.append(f"   - {item.url}")
        if item.citations:
            citations = ", ".join(f"`{citation}`" for citation in item.citations)
            lines.append(f"   - Citations: {citations}")
    return "\n".join(lines) + "\n"


def _coerce_digest(parsed: Any) -> Digest:
    if isinstance(parsed, Digest):
        digest = parsed
    elif isinstance(parsed, dict):
        digest = Digest.model_validate(parsed)
    else:
        raise ProviderValidationError(f"Unsupported parsed payload type: {type(parsed).__name__}")
    if not digest.generated_at:
        digest.generated_at = datetime.now(timezone.utc).isoformat()
    return digest


def _validate_digest_citations(digest: Digest, valid_doc_ids: set[str]) -> None:
    for item in digest.items:
        item_model = DigestItem.model_validate(item)
        if not item_model.citations:
            raise ProviderValidationError("Digest item is missing citations.")
        invalid = [citation for citation in item_model.citations if citation not in valid_doc_ids]
        if invalid:
            raise ProviderValidationError(f"Digest item has invalid citations: {invalid}")
