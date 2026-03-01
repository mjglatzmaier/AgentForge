from __future__ import annotations

import json
from pathlib import Path

from agents.arxiv_research.scoring_step import score_papers


def _papers_payload(count: int = 12) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for index in range(count):
        payload.append(
            {
                "paper_id": f"2401.{index:05d}v1",
                "title": f"LLM Agents Study {index}",
                "authors": ["Alice", "Bob"],
                "abstract": (
                    "This paper studies llm agents with ablation and benchmark results. "
                    "Code on GitHub; DOI:10.1000/example."
                ),
                "categories": ["cs.AI", "cs.LG"],
                "published": f"2026-01-{(index % 28) + 1:02d}T00:00:00Z",
            }
        )
    return payload


def test_scoring_replay_integration_is_deterministic_for_larger_candidate_set(
    tmp_path: Path,
) -> None:
    papers_path = tmp_path / "fixtures" / "papers_raw_large.json"
    papers_path.parent.mkdir(parents=True, exist_ok=True)
    papers_path.write_text(json.dumps(_papers_payload(12)), encoding="utf-8")

    config = {
        "mode": "replay",
        "scoring": {
            "select_m": 8,
            "top_k": 5,
            "min_score_threshold": 0.0,
            "topic_alignment": {"keywords": ["llm", "agents"], "phrases": ["ablation"]},
        },
    }
    result_a = score_papers(
        {
            "step_dir": str(tmp_path / "run_a"),
            "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
            "config": config,
        }
    )
    result_b = score_papers(
        {
            "step_dir": str(tmp_path / "run_b"),
            "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
            "config": config,
        }
    )

    names_a = [item["name"] for item in result_a["outputs"]]
    names_b = [item["name"] for item in result_b["outputs"]]
    assert len(names_a) == len(set(names_a))
    assert names_a == names_b

    selected_a = json.loads((tmp_path / "run_a" / "outputs" / "papers_selected.json").read_text(encoding="utf-8"))
    selected_b = json.loads((tmp_path / "run_b" / "outputs" / "papers_selected.json").read_text(encoding="utf-8"))
    diagnostics_a = json.loads(
        (tmp_path / "run_a" / "outputs" / "scoring_diagnostics.json").read_text(encoding="utf-8")
    )
    diagnostics_b = json.loads(
        (tmp_path / "run_b" / "outputs" / "scoring_diagnostics.json").read_text(encoding="utf-8")
    )

    assert len(selected_a) == 5
    assert selected_a == selected_b
    assert diagnostics_a == diagnostics_b
