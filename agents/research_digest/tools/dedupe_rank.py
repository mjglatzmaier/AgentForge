from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agents.research_digest.tools.models import Doc

_DEFAULT_KEYWORDS = ("agent", "llm", "evaluation", "benchmark", "reasoning", "retrieval")


def run(ctx: dict[str, Any]) -> dict[str, Any]:
    step_dir = Path(ctx["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    docs_path = Path(ctx["inputs"]["docs_norm"]["abs_path"])
    docs = [Doc.model_validate(item) for item in json.loads(docs_path.read_text(encoding="utf-8"))]
    deduped_by_url: dict[str, Doc] = {}
    for doc in docs:
        deduped_by_url.setdefault(doc.url, doc)
    deduped_docs = list(deduped_by_url.values())

    config = ctx.get("config", {})
    keywords = [str(value).lower() for value in config.get("keywords", _DEFAULT_KEYWORDS)]
    for doc in deduped_docs:
        text = f"{doc.title} {doc.summary}".lower()
        doc.score = float(sum(1 for keyword in keywords if keyword in text))

    ranked = sorted(deduped_docs, key=lambda doc: (-doc.score, doc.title.lower(), doc.url))
    top_k = int(config.get("top_k", len(ranked)))
    if top_k >= 0:
        ranked = ranked[:top_k]

    output_path = outputs_dir / "docs_ranked.json"
    output_path.write_text(
        json.dumps([doc.model_dump(mode="json") for doc in ranked], indent=2),
        encoding="utf-8",
    )
    return {
        "outputs": [{"name": "docs_ranked", "type": "json", "path": "outputs/docs_ranked.json"}],
        "metrics": {"count": len(ranked)},
    }
