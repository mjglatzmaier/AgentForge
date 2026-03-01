from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.arxiv_research.scoring_step import score_papers


def _papers_payload() -> list[dict[str, object]]:
    return [
        {
            "paper_id": "2401.00001v1",
            "title": "Scaling Laws for LLM Agents",
            "authors": ["Alice"],
            "abstract": "We provide ablation and theorem results with code on GitHub.",
            "categories": ["cs.AI"],
            "published": "2026-01-03T00:00:00Z",
        },
        {
            "paper_id": "2401.00002v1",
            "title": "Older baseline paper",
            "authors": ["Bob"],
            "abstract": "A historical baseline.",
            "categories": ["cs.LG"],
            "published": "2024-01-03T00:00:00Z",
        },
    ]


def test_score_papers_writes_expected_outputs_and_metrics(tmp_path: Path) -> None:
    papers_path = tmp_path / "inputs" / "papers_raw.json"
    papers_path.parent.mkdir(parents=True, exist_ok=True)
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")

    result = score_papers(
        {
            "step_dir": str(tmp_path),
            "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
            "config": {
                "scoring": {
                    "select_m": 2,
                    "top_k": 1,
                    "topic_alignment": {"keywords": ["llm", "agent"]},
                }
            },
        }
    )

    assert [item["name"] for item in result["outputs"]] == [
        "papers_scored",
        "papers_selected",
        "scoring_diagnostics",
    ]
    assert result["metrics"]["candidate_count"] == 2
    assert result["metrics"]["selected_count"] == 1

    scored_path = tmp_path / "outputs" / "papers_scored.json"
    selected_path = tmp_path / "outputs" / "papers_selected.json"
    diagnostics_path = tmp_path / "outputs" / "scoring_diagnostics.json"
    assert scored_path.is_file()
    assert selected_path.is_file()
    assert diagnostics_path.is_file()

    scored = json.loads(scored_path.read_text(encoding="utf-8"))
    selected = json.loads(selected_path.read_text(encoding="utf-8"))
    diagnostics = json.loads(diagnostics_path.read_text(encoding="utf-8"))
    assert len(scored) == 2
    assert len(selected) == 1
    assert selected[0]["rank"] == 1
    assert diagnostics["selected_count"] == 1


def test_score_papers_requires_papers_raw_input(tmp_path: Path) -> None:
    with pytest.raises(KeyError, match="papers_raw"):
        score_papers({"step_dir": str(tmp_path), "inputs": {}, "config": {}})
