from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentforge.control.registry import AgentRegistry, build_registry_snapshot
from agentforge.control.runtime import execute_control_run
from agentforge.control.state import persist_control_artifacts
from agentforge.contracts.models import (
    AgentSpec,
    ControlNode,
    ControlNodeState,
    ControlPlan,
    ExecutionRequest,
    ExecutionStatus,
    TriggerKind,
    TriggerSpec,
)


def _entrypoint_success(request: ExecutionRequest) -> dict[str, object]:
    outputs_dir = Path(request.metadata["outputs_dir"])
    outputs_dir.mkdir(parents=True, exist_ok=True)
    (outputs_dir / f"{request.operation}.txt").write_text("ok", encoding="utf-8")
    return {"status": "success", "metrics": {"operation": request.operation}}


def _entrypoint_failure(_request: ExecutionRequest) -> dict[str, object]:
    return {"status": "failed", "error": "simulated failure"}


def _agent_spec(*, agent_id: str, entrypoint: str) -> AgentSpec:
    return AgentSpec.model_validate(
        {
            "agent_id": agent_id,
            "version": "1.0.0",
            "description": "test agent",
            "intents": ["test"],
            "tags": ["runtime"],
            "input_contracts": ["Req"],
            "output_contracts": ["Res"],
            "runtime": {
                "runtime": "python",
                "entrypoint": entrypoint,
                "timeout_s": 30,
                "max_concurrency": 1,
            },
            "operations_policy": {
                "terminal_access": "none",
                "allowed_commands": [],
                "fs_scope": [],
                "network_access": "none",
                "network_allowlist": [],
            },
        }
    )


def _persist_run_artifacts(
    *,
    run_dir: Path,
    plan: ControlPlan,
    registry: AgentRegistry,
) -> None:
    persist_control_artifacts(
        run_dir,
        plan=plan,
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        registry=build_registry_snapshot(registry),
    )


def test_execute_control_run_executes_ready_nodes_and_persists_transitions(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-001"
    plan = ControlPlan(
        plan_id="plan-1",
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        nodes=[
            ControlNode(node_id="fetch", agent_id="agent.test", operation="fetch_and_snapshot"),
            ControlNode(
                node_id="synthesize",
                agent_id="agent.test",
                operation="synthesize_digest",
                depends_on=["fetch"],
            ),
        ],
        max_parallel=1,
    )
    registry = AgentRegistry(
        agents_by_id={
            "agent.test": _agent_spec(
                agent_id="agent.test",
                entrypoint="agentforge.tests.control.test_runtime:_entrypoint_success",
            )
        },
        capability_index={},
    )
    _persist_run_artifacts(run_dir=run_dir, plan=plan, registry=registry)

    result = execute_control_run(run_dir)

    assert result.plan_id == "plan-1"
    assert result.node_states == {
        "fetch": ControlNodeState.SUCCEEDED,
        "synthesize": ControlNodeState.SUCCEEDED,
    }
    assert set(result.node_results.keys()) == {"fetch", "synthesize"}
    assert all(item.status is ExecutionStatus.SUCCESS for item in result.node_results.values())

    runtime_state = json.loads((run_dir / "control" / "runtime_state.json").read_text(encoding="utf-8"))
    assert runtime_state["node_states"] == {"fetch": "succeeded", "synthesize": "succeeded"}
    assert (run_dir / "steps" / "00_fetch" / "outputs").is_dir()
    assert (run_dir / "steps" / "01_synthesize" / "outputs").is_dir()


def test_execute_control_run_marks_failed_result_state(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-002"
    plan = ControlPlan(
        plan_id="plan-2",
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        nodes=[ControlNode(node_id="fetch", agent_id="agent.test", operation="fetch_and_snapshot")],
    )
    registry = AgentRegistry(
        agents_by_id={
            "agent.test": _agent_spec(
                agent_id="agent.test",
                entrypoint="agentforge.tests.control.test_runtime:_entrypoint_failure",
            )
        },
        capability_index={},
    )
    _persist_run_artifacts(run_dir=run_dir, plan=plan, registry=registry)

    result = execute_control_run(run_dir)

    assert result.node_states == {"fetch": ControlNodeState.FAILED}
    assert result.node_results["fetch"].status is ExecutionStatus.FAILED
    runtime_state = json.loads((run_dir / "control" / "runtime_state.json").read_text(encoding="utf-8"))
    assert runtime_state["node_states"] == {"fetch": "failed"}


def test_execute_control_run_fails_when_agent_missing_from_registry(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-003"
    plan = ControlPlan(
        plan_id="plan-3",
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        nodes=[ControlNode(node_id="fetch", agent_id="agent.missing", operation="fetch_and_snapshot")],
    )
    _persist_run_artifacts(
        run_dir=run_dir,
        plan=plan,
        registry=AgentRegistry(agents_by_id={}, capability_index={}),
    )

    with pytest.raises(ValueError, match="AgentSpec not found"):
        execute_control_run(run_dir)
