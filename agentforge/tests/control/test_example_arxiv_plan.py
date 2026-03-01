from __future__ import annotations

from pathlib import Path

import yaml

from agentforge.contracts.models import ControlPlan


def test_arxiv_digest_example_plan_validates_as_control_plan() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    plan_path = repo_root / "examples" / "arxiv_digest_plan.yaml"

    payload = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
    plan = ControlPlan.model_validate(payload)

    assert plan.plan_id == "arxiv-digest-demo-v1"
    assert [node.node_id for node in plan.nodes] == [
        "fetch_and_snapshot",
        "synthesize_digest",
        "render_report",
        "local_write_delivery",
    ]
    assert plan.nodes[0].metadata["mode"] == "live"
    assert plan.nodes[1].depends_on == ["fetch_and_snapshot"]
    assert plan.nodes[2].depends_on == ["synthesize_digest"]
