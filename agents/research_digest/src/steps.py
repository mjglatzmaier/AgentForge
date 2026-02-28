from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.research_digest.tools import arxiv as arxiv_tool
from agents.research_digest.tools import dedupe_rank as dedupe_rank_tool
from agents.research_digest.tools import normalize as normalize_tool
from agents.research_digest.tools import render as render_tool
from agents.research_digest.tools import rss as rss_tool


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
    tool_ctx = dict(ctx)
    tool_ctx["inputs"] = {"docs_ranked": _require_input(ctx, "docs_ranked")}
    render_tool.run(tool_ctx)
    step_dir = Path(ctx["step_dir"])
    digest = json.loads((step_dir / "outputs" / "digest.json").read_text(encoding="utf-8"))
    return {
        "outputs": [
            {"name": "digest_json", "type": "json", "path": "outputs/digest.json"},
            {"name": "digest_md", "type": "markdown", "path": "outputs/digest.md"},
        ],
        "metrics": {"count": len(digest.get("items", []))},
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
