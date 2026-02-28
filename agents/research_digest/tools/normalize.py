from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from agents.research_digest.tools.models import ArxivPaper, Doc, RSSItem


def run(ctx: dict[str, Any]) -> dict[str, Any]:
    step_dir = Path(ctx["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    inputs = ctx.get("inputs", {})
    arxiv_path = Path(inputs["arxiv_docs"]["abs_path"])
    rss_path = Path(inputs["rss_docs"]["abs_path"])
    arxiv_docs = [ArxivPaper.model_validate(item) for item in json.loads(arxiv_path.read_text(encoding="utf-8"))]
    rss_docs = [RSSItem.model_validate(item) for item in json.loads(rss_path.read_text(encoding="utf-8"))]

    normalized: list[Doc] = []
    for paper in arxiv_docs:
        normalized.append(
            Doc(
                doc_id=_doc_id(paper.url),
                title=paper.title,
                url=paper.url,
                summary=paper.abstract,
                published=paper.published,
                source="arxiv",
            )
        )
    for item in rss_docs:
        normalized.append(
            Doc(
                doc_id=_doc_id(item.url),
                title=item.title,
                url=item.url,
                summary=item.snippet,
                published=item.published,
                source="rss",
            )
        )

    output_path = outputs_dir / "docs_norm.json"
    output_path.write_text(
        json.dumps([doc.model_dump(mode="json") for doc in normalized], indent=2),
        encoding="utf-8",
    )
    return {
        "outputs": [{"name": "docs_norm", "type": "json", "path": "outputs/docs_norm.json"}],
        "metrics": {"count": len(normalized)},
    }


def _doc_id(url: str) -> str:
    return f"doc-{hashlib.sha256(url.encode('utf-8')).hexdigest()[:12]}"
