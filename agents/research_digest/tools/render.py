from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from agents.research_digest.tools.models import Digest, DigestItem, Doc


def run(ctx: dict[str, Any]) -> dict[str, Any]:
    step_dir = Path(ctx["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    ranked_path = Path(ctx["inputs"]["docs_ranked"]["abs_path"])
    docs = [Doc.model_validate(item) for item in json.loads(ranked_path.read_text(encoding="utf-8"))]
    top_n = int(ctx.get("config", {}).get("top_n", 10))
    selected_docs = docs[:top_n] if top_n >= 0 else docs

    digest = Digest(
        generated_at=datetime.now(timezone.utc).isoformat(),
        items=[
            DigestItem(
                doc_id=doc.doc_id,
                title=doc.title,
                url=doc.url,
                summary=doc.summary,
                source=doc.source,
                score=doc.score,
                published=doc.published,
                citations=[doc.doc_id],
            )
            for doc in selected_docs
        ],
    )

    digest_json_path = outputs_dir / "digest.json"
    digest_json_path.write_text(json.dumps(digest.model_dump(mode="json"), indent=2), encoding="utf-8")

    digest_md_path = outputs_dir / "digest.md"
    digest_md_path.write_text(_to_markdown(digest), encoding="utf-8")

    return {
        "outputs": [
            {"name": "digest_md", "type": "markdown", "path": "outputs/digest.md"},
            {"name": "digest_json", "type": "json", "path": "outputs/digest.json"},
        ],
        "metrics": {"count": len(digest.items)},
    }


def _to_markdown(digest: Digest) -> str:
    lines = [f"# {digest.title}", "", f"Generated: {digest.generated_at}", ""]
    if not digest.items:
        lines.append("- No items found.")
        return "\n".join(lines) + "\n"

    for idx, item in enumerate(digest.items, start=1):
        lines.append(f"{idx}. **{item.title}** ({item.source}, score={item.score:.1f})")
        lines.append(f"   - doc_id: `{item.doc_id}`")
        lines.append(f"   - {item.summary}")
        lines.append(f"   - {item.url}")
    return "\n".join(lines) + "\n"
