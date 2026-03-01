from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentforge.control.events import load_control_events
from agentforge.control.registry import AgentRegistry, build_registry_snapshot
from agentforge.control.runtime import execute_control_run
from agentforge.control.state import persist_control_artifacts
from agentforge.storage.hashing import sha256_file
from agentforge.storage.manifest import load_manifest
from agentforge.contracts.models import (
    ArtifactRef,
    AgentSpec,
    ControlEventType,
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


def _entrypoint_emits_artifact(request: ExecutionRequest) -> dict[str, object]:
    outputs_dir = Path(request.metadata["outputs_dir"])
    outputs_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{request.operation}.txt"
    artifact_name = str(request.metadata.get("output_name", f"{request.operation}_txt"))
    content = f"artifact for {request.operation}"
    file_path = outputs_dir / file_name
    file_path.write_text(content, encoding="utf-8")
    artifact = ArtifactRef(
        name=artifact_name,
        type="text",
        path=f"outputs/{file_name}",
        sha256=sha256_file(file_path),
        producer_step_id="ignored",
    )
    return {"status": "success", "produced_artifacts": [artifact]}


def _entrypoint_fail_once_then_success(request: ExecutionRequest) -> dict[str, object]:
    step_dir = Path(request.metadata["step_dir"])
    attempts_file = step_dir / "attempts.txt"
    attempt_count = 0
    if attempts_file.exists():
        attempt_count = int(attempts_file.read_text(encoding="utf-8"))
    attempts_file.write_text(str(attempt_count + 1), encoding="utf-8")
    if attempt_count == 0:
        return {"status": "failed", "error": "transient"}
    return _entrypoint_emits_artifact(request)


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
            ControlNode(
                node_id="fetch",
                agent_id="agent.test",
                operation="fetch_and_snapshot",
                metadata={"output_name": "papers_raw"},
            ),
            ControlNode(
                node_id="synthesize",
                agent_id="agent.test",
                operation="synthesize_digest",
                depends_on=["fetch"],
                inputs=["papers_raw"],
                metadata={"output_name": "digest_json"},
            ),
        ],
        max_parallel=1,
    )
    registry = AgentRegistry(
        agents_by_id={
            "agent.test": _agent_spec(
                agent_id="agent.test",
                entrypoint="agentforge.tests.control.test_runtime:_entrypoint_emits_artifact",
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
    manifest = load_manifest(run_dir / "manifest.json")
    assert [artifact.name for artifact in manifest.artifacts] == ["papers_raw", "digest_json"]
    assert manifest.artifacts[0].path == "steps/00_fetch/outputs/fetch_and_snapshot.txt"
    assert manifest.artifacts[0].producer_step_id == "fetch"
    assert manifest.artifacts[1].path == "steps/01_synthesize/outputs/synthesize_digest.txt"
    assert manifest.artifacts[1].producer_step_id == "synthesize"
    events = load_control_events(run_dir)
    assert [event.event_type for event in events] == [
        ControlEventType.NODE_READY,
        ControlEventType.NODE_STARTED,
        ControlEventType.NODE_SUCCEEDED,
        ControlEventType.NODE_READY,
        ControlEventType.NODE_STARTED,
        ControlEventType.NODE_SUCCEEDED,
    ]
    snapshot = json.loads((run_dir / "control" / "snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["node_states"] == {"fetch": "succeeded", "synthesize": "succeeded"}
    assert snapshot["last_event_id"] == events[-1].event_id


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
    events = load_control_events(run_dir)
    assert [event.event_type for event in events] == [
        ControlEventType.NODE_READY,
        ControlEventType.NODE_STARTED,
        ControlEventType.NODE_FAILED,
    ]
    snapshot = json.loads((run_dir / "control" / "snapshot.json").read_text(encoding="utf-8"))
    assert snapshot["node_states"] == {"fetch": "failed"}
    assert snapshot["last_event_id"] == events[-1].event_id


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


def test_execute_control_run_rejects_duplicate_artifact_names(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-004"
    plan = ControlPlan(
        plan_id="plan-4",
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        nodes=[
            ControlNode(
                node_id="first",
                agent_id="agent.test",
                operation="op_first",
                metadata={"output_name": "dup_artifact"},
            ),
            ControlNode(
                node_id="second",
                agent_id="agent.test",
                operation="op_second",
                depends_on=["first"],
                metadata={"output_name": "dup_artifact"},
            ),
        ],
    )
    registry = AgentRegistry(
        agents_by_id={
            "agent.test": _agent_spec(
                agent_id="agent.test",
                entrypoint="agentforge.tests.control.test_runtime:_entrypoint_emits_artifact",
            )
        },
        capability_index={},
    )
    _persist_run_artifacts(run_dir=run_dir, plan=plan, registry=registry)

    with pytest.raises(ValueError, match="Artifact already registered"):
        execute_control_run(run_dir)


def test_execute_control_run_requires_manifest_input_artifacts(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-005"
    plan = ControlPlan(
        plan_id="plan-5",
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        nodes=[
            ControlNode(
                node_id="synthesize",
                agent_id="agent.test",
                operation="synthesize_digest",
                inputs=["papers_raw"],
            )
        ],
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

    with pytest.raises(KeyError, match="requires missing manifest artifact"):
        execute_control_run(run_dir)


def test_execute_control_run_emits_retry_attempt_metadata_on_retry(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-006"
    plan = ControlPlan(
        plan_id="plan-6",
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        nodes=[
            ControlNode(
                node_id="fetch",
                agent_id="agent.test",
                operation="fetch_and_snapshot",
                retry_policy={"transient_max_retries": 2},
                metadata={"output_name": "papers_raw"},
            )
        ],
    )
    registry = AgentRegistry(
        agents_by_id={
            "agent.test": _agent_spec(
                agent_id="agent.test",
                entrypoint="agentforge.tests.control.test_runtime:_entrypoint_fail_once_then_success",
            )
        },
        capability_index={},
    )
    _persist_run_artifacts(run_dir=run_dir, plan=plan, registry=registry)

    result = execute_control_run(run_dir)

    assert result.node_states == {"fetch": ControlNodeState.SUCCEEDED}
    events = load_control_events(run_dir)
    ready_retry_events = [
        event
        for event in events
        if event.event_type is ControlEventType.NODE_READY and event.payload.get("retry_attempt") == 1
    ]
    assert ready_retry_events


def test_execute_control_run_uses_container_adapter_and_returns_explicit_unsupported_error(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "runs" / "run-007"
    plan = ControlPlan(
        plan_id="plan-7",
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        nodes=[ControlNode(node_id="container_node", agent_id="agent.container", operation="pipeline")],
    )
    container_spec = AgentSpec.model_validate(
        {
            "agent_id": "agent.container",
            "version": "1.0.0",
            "description": "container agent",
            "intents": ["test"],
            "tags": ["container"],
            "input_contracts": ["Req"],
            "output_contracts": ["Res"],
            "runtime": {
                "runtime": "container",
                "type": "container",
                "entrypoint": "unused.container.entrypoint",
                "container": {
                    "image": "ghcr.io/example/container-agent:1.0.0",
                    "command": ["python", "-m", "entrypoint"],
                    "env": {"PYTHONUNBUFFERED": "1"},
                    "io_contract": "json-stdio",
                },
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
    registry = AgentRegistry(
        agents_by_id={"agent.container": container_spec},
        capability_index={},
    )
    _persist_run_artifacts(run_dir=run_dir, plan=plan, registry=registry)

    result = execute_control_run(run_dir)

    assert result.node_states == {"container_node": ControlNodeState.FAILED}
    assert result.node_results["container_node"].status is ExecutionStatus.FAILED
    assert result.node_results["container_node"].error is not None
    assert "Unsupported runtime for V1" in result.node_results["container_node"].error
