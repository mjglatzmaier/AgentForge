from __future__ import annotations

import json
from pathlib import Path

from agentforge.contracts.models import ArtifactRef, Manifest
from agentforge.sidecar.agentd.api.approvals_api import approve_approval
from agentforge.sidecar.agentd.approvals.store_v1 import ApprovalGatewayV1
from agentforge.sidecar.agentd.broker.events_store import append_run_event, create_run_event
from agentforge.sidecar.core.contracts.events_v1 import RunEventType
from agentforge.sidecar.core.contracts.operator_auth_v1 import OperatorAuthContextV1
from agentforge.sidecar.core.contracts.tool_contract_v1 import ToolCallRequestV1
from agentforge.sidecar.workbench import (
    build_approval_modal,
    build_artifact_viewer,
    build_event_timeline,
    build_run_detail_panel,
    build_run_graph_panel,
    build_runs_panel,
)


def test_runs_panel_and_timeline_projection(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run_a"
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "control").mkdir(parents=True, exist_ok=True)
    (run_dir / "control" / "plan.json").write_text(
        json.dumps(
            {
                "plan_id": "plan_a",
                "nodes": [
                    {
                        "node_id": "fetch",
                        "agent_id": "agent.fetch",
                        "operation": "fetch_and_snapshot",
                        "depends_on": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "control" / "snapshot.json").write_text(
        json.dumps(
            {
                "plan_id": "plan_a",
                "last_event_id": "evt_terminal",
                "summary": {"succeeded": 1, "pending": 0},
                "node_states": {"fetch": "succeeded"},
            }
        ),
        encoding="utf-8",
    )
    append_run_event(
        run_dir,
        create_run_event(run_id="run_a", event_type=RunEventType.RUN_STARTED),
    )

    runs_panel = build_runs_panel(runs_root)
    assert runs_panel.runs[0]["run_id"] == "run_a"
    assert runs_panel.runs[0]["status"] in {"completed", "succeeded"}

    timeline = build_event_timeline(runs_root, run_id="run_a")
    assert timeline.events[0].event_type == RunEventType.RUN_STARTED.value

    detail = build_run_detail_panel(runs_root, run_id="run_a")
    assert detail.status in {"completed", "succeeded"}
    assert detail.plan_id == "plan_a"
    assert detail.node_states["fetch"] == "succeeded"

    graph = build_run_graph_panel(runs_root, run_id="run_a")
    assert graph.nodes[0]["node_id"] == "fetch"
    assert graph.nodes[0]["state"] == "succeeded"


def test_approval_modal_projection(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    gateway = ApprovalGatewayV1(runs_root)
    request = ToolCallRequestV1(
        request_id="req_1",
        run_id="run_a",
        node_id="node_a",
        agent_id="agent_a",
        capability="exchange.read",
        operation="exchange.get_ticker",
        trace={"correlation_id": "corr_1"},
    )
    record = gateway.request(request)
    modal = build_approval_modal(runs_root)
    assert modal.approvals[0].approval_id == record.approval_id
    approve_approval(
        runs_root,
        record.approval_id,
        auth_context=OperatorAuthContextV1(operator_id="operator_1", scopes=["approvals:write"]),
    )
    assert build_approval_modal(runs_root).approvals == []


def test_artifact_viewer_projection(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run_art"
    run_dir.mkdir(parents=True, exist_ok=True)
    outputs_path = run_dir / "steps" / "00_step" / "outputs"
    outputs_path.mkdir(parents=True, exist_ok=True)
    artifact_file = outputs_path / "digest.json"
    artifact_file.write_text("{}", encoding="utf-8")

    manifest = Manifest(
        run_id="run_art",
        artifacts=[
            ArtifactRef(
                name="digest_json",
                type="json",
                path="steps/00_step/outputs/digest.json",
                sha256="abc",
                producer_step_id="step",
            )
        ],
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    viewer = build_artifact_viewer(runs_root, run_id="run_art")
    assert viewer.artifacts[0]["name"] == "digest_json"
    assert viewer.artifacts[0]["local_path"].endswith("steps/00_step/outputs/digest.json")
