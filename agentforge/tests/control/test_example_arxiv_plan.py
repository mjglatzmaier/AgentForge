from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from agentforge.contracts.models import ControlPlan


@pytest.mark.parametrize(
    "plan_name",
    [
        "arxiv_digest_plan.yaml",
        "arxiv_llm_theory_plan.yaml",
        "arxiv_llm_agents_plan.yaml",
        "arxiv_llm_evaluation_plan.yaml",
    ],
)
def test_arxiv_example_plans_validate_as_control_plan(plan_name: str) -> None:
    repo_root = Path(__file__).resolve().parents[3]
    plan_path = repo_root / "examples" / plan_name

    payload = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    plan = ControlPlan.model_validate(payload)

    assert plan.plan_id
    assert [node.node_id for node in plan.nodes] == [
        "fetch_and_snapshot",
        "synthesize_digest",
        "render_report",
        "local_write_delivery",
    ]
    fetch_cfg = plan.nodes[0].metadata["config"]
    assert fetch_cfg["mode"] == "live"
    assert fetch_cfg["query"]
    assert fetch_cfg["categories"]
    assert fetch_cfg["max_results"] >= 1
    assert fetch_cfg["sort_by"] in {"relevance", "lastUpdatedDate"}
    if "ranking" in fetch_cfg:
        weights = fetch_cfg["ranking"]["weights"]
        assert "topic_alignment" in weights
        assert "citations" in weights
        assert "credibility" in weights
    assert plan.nodes[1].depends_on == ["fetch_and_snapshot"]
    assert plan.nodes[2].depends_on == ["synthesize_digest"]
