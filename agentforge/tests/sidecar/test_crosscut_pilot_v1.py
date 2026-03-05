from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentforge.contracts.models import ArtifactRef, Manifest
from agentforge.sidecar.agentd.api.approvals_api import approve_approval, deny_approval, get_approvals
from agentforge.sidecar.agentd.api.artifacts_api import get_run_artifacts
from agentforge.sidecar.agentd.api.events_api import get_run_timeline
from agentforge.sidecar.agentd.api.runs_api import get_run, get_run_graph, get_runs
from agentforge.sidecar.agentd.approvals.store_v1 import ApprovalGatewayV1
from agentforge.sidecar.agentd.broker.audit_store_v1 import load_audit_events
from agentforge.sidecar.agentd.broker.events_store import append_run_event, create_run_event, load_run_events
from agentforge.sidecar.agentd.broker.tool_broker_v1 import ToolBrokerV1
from agentforge.sidecar.core.contracts.events_v1 import RunEventType
from agentforge.sidecar.core.contracts.operator_auth_v1 import OperatorAuthContextV1
from agentforge.sidecar.core.contracts.tool_contract_v1 import (
    ToolCallRequestV1,
    ToolOperationSpecV1,
    ToolSpecV1,
)
from agentforge.sidecar.core.policy import PolicyConfigV1, PolicyEngineV1
from agentforge.sidecar.workbench import (
    build_approval_modal,
    build_artifact_viewer,
    build_event_timeline,
    build_run_detail_panel,
    build_run_graph_panel,
    build_runs_panel,
)


class _FakeInvoker:
    def __init__(self) -> None:
        self.calls = 0

    def invoke(self, _request: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        return {"output": {"order_id": "ord_001", "status": "accepted"}}


def _policy() -> PolicyConfigV1:
    return PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_crosscut_pilot_v1",
            "defaults": {"deny_by_default": True},
            "agents": {
                "agent.trade": {
                    "role": "trader",
                    "allowed_capabilities": ["exchange.trade"],
                    "approval_required_ops": ["exchange.place_order"],
                    "constraints": {
                        "exchange.place_order": {
                            "symbol_allowlist": ["btc-usd"],
                            "max_notional_usd": 1000.0,
                        }
                    },
                }
            },
        }
    )


def _tool_spec() -> ToolSpecV1:
    return ToolSpecV1(
        name="exchange-tool",
        version="1.0.0",
        operations=[
            ToolOperationSpecV1(
                op_id="exchange.place_order",
                required_capabilities=["exchange.trade"],
                input_schema={
                    "symbol": "str",
                    "notional_usd": "float",
                    "api_key": "str",
                    "headers": "object",
                },
                output_schema={"order_id": "str", "status": "str"},
                timeout_s=1.0,
                max_retries=0,
            )
        ],
    )


def _request(run_id: str, request_id: str) -> ToolCallRequestV1:
    return ToolCallRequestV1(
        request_id=request_id,
        run_id=run_id,
        node_id="node_execute_order",
        agent_id="agent.trade",
        capability="exchange.trade",
        operation="exchange.place_order",
        input={
            "symbol": "btc-usd",
            "notional_usd": 250.0,
            "api_key": "plain-key",
            "headers": {"authorization": "Bearer secret-token"},
        },
        trace={"correlation_id": "corr_crosscut_1"},
    )


def _persist_run_outputs(runs_root: Path, *, run_id: str) -> None:
    run_dir = runs_root / run_id
    control_dir = run_dir / "control"
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "plan.json").write_text(
        json.dumps(
            {
                "plan_id": "pilot_plan_v1",
                "nodes": [
                    {
                        "node_id": "node_analyze",
                        "agent_id": "agent.research",
                        "operation": "analyze_market",
                        "depends_on": [],
                    },
                    {
                        "node_id": "node_execute_order",
                        "agent_id": "agent.trade",
                        "operation": "exchange.place_order",
                        "depends_on": ["node_analyze"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (control_dir / "snapshot.json").write_text(
        json.dumps(
            {
                "plan_id": "pilot_plan_v1",
                "summary": {"succeeded": 2, "pending": 0},
                "node_states": {
                    "node_analyze": "succeeded",
                    "node_execute_order": "succeeded",
                },
            }
        ),
        encoding="utf-8",
    )

    outputs_dir = run_dir / "steps" / "01_execute_order" / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    artifact_path = outputs_dir / "order_result.json"
    artifact_path.write_text(
        json.dumps({"order_id": "ord_001", "status": "accepted", "symbol": "btc-usd"}),
        encoding="utf-8",
    )
    manifest = Manifest(
        run_id=run_id,
        artifacts=[
            ArtifactRef(
                name="order_result_json",
                type="json",
                path="steps/01_execute_order/outputs/order_result.json",
                sha256="sha-order-result",
                producer_step_id="node_execute_order",
            )
        ],
    )
    (run_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    append_run_event(
        run_dir,
        create_run_event(
            run_id=run_id,
            event_type=RunEventType.ARTIFACT_WRITTEN,
            payload={
                "artifact_name": "order_result_json",
                "path": "steps/01_execute_order/outputs/order_result.json",
            },
        ),
    )


def _run_allow_branch(runs_root: Path, *, run_id: str, request_id: str) -> list[str]:
    invoker = _FakeInvoker()
    approval_gateway = ApprovalGatewayV1(runs_root)
    broker = ToolBrokerV1(
        runs_root=runs_root,
        tool_spec=_tool_spec(),
        connector_invoker=invoker,
        policy_engine=PolicyEngineV1(_policy()),
        approval_gateway=approval_gateway,
    )
    request = _request(run_id, request_id)

    initial = broker.dispatch(request, allowed_capabilities=["exchange.trade"])
    assert initial.status == "approval_required"
    assert initial.error is not None
    approval_id = initial.error.details["approval_id"]
    assert isinstance(approval_id, str)
    approve_approval(
        runs_root,
        approval_id,
        auth_context=OperatorAuthContextV1(operator_id="operator_1", scopes=["approvals:write"]),
    )
    approval_record = approval_gateway.get(approval_id)
    assert approval_record is not None
    assert approval_record.approval_token_id is not None

    executed = broker.dispatch(
        request.model_copy(update={"approval_token": approval_record.approval_token_id}),
        allowed_capabilities=["exchange.trade"],
    )
    assert executed.status == "ok"
    assert executed.output["order_id"] == "ord_001"
    assert invoker.calls == 1
    _persist_run_outputs(runs_root, run_id=run_id)
    return [event.event_type.value for event in load_run_events(runs_root / run_id)]


def test_crosscut_pilot_flow_validates_deny_allow_observability_and_workbench(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    deny_run_id = "run_crosscut_deny"
    allow_run_id = "run_crosscut_allow"
    deny_request = _request(deny_run_id, "req_crosscut_deny")

    deny_invoker = _FakeInvoker()
    deny_gateway = ApprovalGatewayV1(runs_root)
    deny_broker = ToolBrokerV1(
        runs_root=runs_root,
        tool_spec=_tool_spec(),
        connector_invoker=deny_invoker,
        policy_engine=PolicyEngineV1(_policy()),
        approval_gateway=deny_gateway,
    )

    first = deny_broker.dispatch(deny_request, allowed_capabilities=["exchange.trade"])
    assert first.status == "approval_required"
    assert first.error is not None
    deny_approval_id = first.error.details["approval_id"]
    assert isinstance(deny_approval_id, str)
    deny_approval(
        runs_root,
        deny_approval_id,
        auth_context=OperatorAuthContextV1(operator_id="operator_1", scopes=["approvals:write"]),
    )
    denied = deny_broker.dispatch(deny_request, allowed_capabilities=["exchange.trade"])
    assert denied.status == "denied"
    assert denied.error is not None
    assert denied.error.code == "POLICY_DENIED"
    assert deny_invoker.calls == 0

    allow_event_types = _run_allow_branch(
        runs_root,
        run_id=allow_run_id,
        request_id="req_crosscut_allow",
    )
    assert RunEventType.APPROVAL_REQUESTED.value in allow_event_types
    assert RunEventType.APPROVAL_TOKEN_ISSUED.value in allow_event_types
    assert RunEventType.APPROVAL_TOKEN_USED.value in allow_event_types
    assert RunEventType.ARTIFACT_WRITTEN.value in allow_event_types

    approvals = get_approvals(runs_root).approvals
    assert approvals == []
    assert build_approval_modal(runs_root).approvals == []

    runs_panel = build_runs_panel(runs_root)
    assert {item["run_id"] for item in runs_panel.runs} >= {deny_run_id, allow_run_id}
    runs_listing = get_runs(runs_root)
    assert {item.run_id for item in runs_listing.runs} >= {deny_run_id, allow_run_id}

    run_detail = get_run(runs_root, run_id=allow_run_id)
    assert run_detail.status == "succeeded"
    assert run_detail.node_states["node_execute_order"] == "succeeded"
    detail_panel = build_run_detail_panel(runs_root, run_id=allow_run_id)
    assert detail_panel.plan_id == "pilot_plan_v1"

    graph = get_run_graph(runs_root, run_id=allow_run_id)
    assert [node.node_id for node in graph.nodes] == ["node_analyze", "node_execute_order"]
    graph_panel = build_run_graph_panel(runs_root, run_id=allow_run_id)
    assert graph_panel.nodes[1]["depends_on"] == ["node_analyze"]

    timeline = get_run_timeline(runs_root, run_id=allow_run_id, limit=100)
    assert [event.event_type for event in timeline.events][:3] == [
        RunEventType.TOOL_CALL_REQUESTED.value,
        RunEventType.APPROVAL_REQUESTED.value,
        RunEventType.TOOL_CALL_COMPLETED.value,
    ]
    timeline_panel = build_event_timeline(runs_root, run_id=allow_run_id, limit=100)
    assert timeline_panel.events[-1].event_type == RunEventType.ARTIFACT_WRITTEN.value

    artifacts = get_run_artifacts(runs_root, run_id=allow_run_id)
    assert [(item.name, item.path) for item in artifacts.artifacts] == [
        ("order_result_json", "steps/01_execute_order/outputs/order_result.json")
    ]
    artifact_panel = build_artifact_viewer(runs_root, run_id=allow_run_id)
    assert artifact_panel.artifacts[0]["name"] == "order_result_json"

    events_text = (runs_root / allow_run_id / "events.jsonl").read_text(encoding="utf-8")
    audit_text = (runs_root / "_audit" / "audit.jsonl").read_text(encoding="utf-8")
    assert "plain-key" not in events_text
    assert "secret-token" not in events_text
    assert "plain-key" not in audit_text
    assert "secret-token" not in audit_text
    assert "[REDACTED]" in events_text
    assert "[REDACTED]" in audit_text

    audit_by_run = [event for event in load_audit_events(runs_root) if event.run_id == allow_run_id]
    decisions = {event.decision for event in audit_by_run}
    assert {"allow", "require_approval"} <= decisions
    for event in audit_by_run:
        token_value = event.details.get("approval_token")
        if token_value is not None:
            assert token_value == "[REDACTED]"

    bad_run = runs_root / "run_crosscut_bad_artifact"
    bad_run.mkdir(parents=True, exist_ok=True)
    (bad_run / "manifest.json").write_text(
        Manifest(
            run_id="run_crosscut_bad_artifact",
            artifacts=[
                ArtifactRef(
                    name="bad",
                    type="txt",
                    path="../outside.txt",
                    sha256="bad",
                    producer_step_id="step_bad",
                )
            ],
        ).model_dump_json(indent=2),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="escapes run directory"):
        get_run_artifacts(runs_root, run_id="run_crosscut_bad_artifact")


def test_crosscut_pilot_replay_is_deterministic_for_same_input_and_policy(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    first_event_types = _run_allow_branch(
        runs_root,
        run_id="run_crosscut_replay_1",
        request_id="req_crosscut_replay",
    )
    second_event_types = _run_allow_branch(
        runs_root,
        run_id="run_crosscut_replay_2",
        request_id="req_crosscut_replay",
    )

    first_detail = get_run(runs_root, run_id="run_crosscut_replay_1")
    second_detail = get_run(runs_root, run_id="run_crosscut_replay_2")
    assert first_detail.node_states == second_detail.node_states
    assert first_detail.summary == second_detail.summary
    assert first_detail.status == second_detail.status == "succeeded"

    first_graph = get_run_graph(runs_root, run_id="run_crosscut_replay_1")
    second_graph = get_run_graph(runs_root, run_id="run_crosscut_replay_2")
    assert [(item.node_id, item.state, tuple(item.depends_on)) for item in first_graph.nodes] == [
        (item.node_id, item.state, tuple(item.depends_on)) for item in second_graph.nodes
    ]

    first_artifacts = get_run_artifacts(runs_root, run_id="run_crosscut_replay_1")
    second_artifacts = get_run_artifacts(runs_root, run_id="run_crosscut_replay_2")
    assert [(item.name, item.type, item.path) for item in first_artifacts.artifacts] == [
        (item.name, item.type, item.path) for item in second_artifacts.artifacts
    ]

    assert first_event_types == second_event_types
