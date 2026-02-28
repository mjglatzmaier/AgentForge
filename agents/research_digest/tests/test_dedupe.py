from __future__ import annotations

import json
from pathlib import Path

from agents.research_digest.tools import dedupe_rank


def test_dedupe_rank_is_stable_and_deduplicates_by_url(tmp_path: Path) -> None:
    docs = [
        {
            "doc_id": "a",
            "title": "Agent Evaluation Basics",
            "url": "https://example.com/a",
            "summary": "Agent benchmarking guide",
            "published": "2026-01-01",
            "source": "rss",
            "score": 0.0,
        },
        {
            "doc_id": "a-dup",
            "title": "Agent Evaluation Basics Duplicate",
            "url": "https://example.com/a",
            "summary": "duplicate url should be removed",
            "published": "2026-01-02",
            "source": "rss",
            "score": 0.0,
        },
        {
            "doc_id": "b",
            "title": "Reasoning with LLM Agents",
            "url": "https://example.com/b",
            "summary": "llm reasoning and agent planning",
            "published": "2026-01-03",
            "source": "arxiv",
            "score": 0.0,
        },
    ]
    docs_path = tmp_path / "docs_norm.json"
    docs_path.write_text(json.dumps(docs), encoding="utf-8")

    step_dir_a = tmp_path / "step_a"
    step_dir_b = tmp_path / "step_b"
    ctx_a = {
        "step_dir": str(step_dir_a),
        "inputs": {"docs_norm": {"abs_path": str(docs_path)}},
        "config": {"keywords": ["agent", "llm", "reasoning"]},
    }
    ctx_b = {
        "step_dir": str(step_dir_b),
        "inputs": {"docs_norm": {"abs_path": str(docs_path)}},
        "config": {"keywords": ["agent", "llm", "reasoning"]},
    }

    dedupe_rank.run(ctx_a)
    dedupe_rank.run(ctx_b)

    ranked_a = json.loads((step_dir_a / "outputs" / "docs_ranked.json").read_text(encoding="utf-8"))
    ranked_b = json.loads((step_dir_b / "outputs" / "docs_ranked.json").read_text(encoding="utf-8"))

    assert len(ranked_a) == 2
    assert ranked_a == ranked_b
    assert ranked_a[0]["url"] == "https://example.com/b"
