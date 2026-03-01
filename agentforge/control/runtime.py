"""Control-plane run executor."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from agentforge.control.adapters import (
    CommandRuntimeAdapter,
    ContainerRuntimeAdapter,
    PythonRuntimeAdapter,
    RuntimeAdapter,
)
from agentforge.control.registry import AgentRegistry
from agentforge.control.scheduler import plan_scheduler_tick
from agentforge.contracts.models import (
    AgentRuntimeKind,
    AgentSpec,
    ControlNode,
    ControlNodeState,
    ControlPlan,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)


@dataclass(frozen=True)
class ControlRunExecution:
    """Final node states and execution results for one control-plan run."""

    plan_id: str
    node_states: dict[str, ControlNodeState]
    node_results: dict[str, ExecutionResult]


def execute_control_run(
    run_dir: str | Path,
    *,
    runtime_adapters: Mapping[AgentRuntimeKind, RuntimeAdapter] | None = None,
    retry_counts: Mapping[str, int] | None = None,
) -> ControlRunExecution:
    """Execute one control plan from persisted run artifacts."""

    run_path = Path(run_dir)
    plan = _load_control_plan(run_path)
    registry = _load_registry_snapshot(run_path)
    adapters = dict(runtime_adapters or _default_runtime_adapters())
    nodes_by_id = {node.node_id: node for node in plan.nodes}
    node_index = {node.node_id: i for i, node in enumerate(plan.nodes)}

    node_states = {node.node_id: node.state for node in plan.nodes}
    node_results: dict[str, ExecutionResult] = {}
    _persist_runtime_state(run_path, plan=plan, node_states=node_states)

    while True:
        before_tick = dict(node_states)
        tick = plan_scheduler_tick(
            plan,
            node_states=node_states,
            retry_counts=retry_counts,
        )
        node_states = dict(tick.node_states)
        if node_states != before_tick:
            _persist_runtime_state(run_path, plan=plan, node_states=node_states)

        if not tick.dispatch_node_ids:
            break

        for node_id in tick.dispatch_node_ids:
            node = nodes_by_id[node_id]
            spec = registry.get(node.agent_id)
            if spec is None:
                raise ValueError(f"AgentSpec not found in registry for node '{node_id}': {node.agent_id}")

            adapter = adapters.get(spec.runtime.runtime)
            if adapter is None:
                raise ValueError(
                    f"No RuntimeAdapter configured for runtime '{spec.runtime.runtime.value}'."
                )

            node_states[node_id] = ControlNodeState.RUNNING
            _persist_runtime_state(run_path, plan=plan, node_states=node_states)

            request = _build_execution_request(
                run_path=run_path,
                node=node,
                node_index=node_index[node_id],
                spec=spec,
            )
            result = adapter.execute(request)
            node_results[node_id] = result

            node_states[node_id] = (
                ControlNodeState.SUCCEEDED
                if result.status is ExecutionStatus.SUCCESS
                else ControlNodeState.FAILED
            )
            _persist_runtime_state(run_path, plan=plan, node_states=node_states)

    return ControlRunExecution(
        plan_id=plan.plan_id,
        node_states=node_states,
        node_results=node_results,
    )


def _default_runtime_adapters() -> dict[AgentRuntimeKind, RuntimeAdapter]:
    return {
        AgentRuntimeKind.PYTHON: PythonRuntimeAdapter(),
        AgentRuntimeKind.COMMAND: CommandRuntimeAdapter(),
        AgentRuntimeKind.CONTAINER: ContainerRuntimeAdapter(),
    }


def _build_execution_request(
    *,
    run_path: Path,
    node: ControlNode,
    node_index: int,
    spec: AgentSpec,
) -> ExecutionRequest:
    step_dir = run_path / "steps" / f"{node_index:02d}_{node.node_id}"
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    metadata = dict(node.metadata)
    metadata.setdefault("run_dir", str(run_path))
    metadata.setdefault("step_dir", str(step_dir))
    metadata.setdefault("outputs_dir", str(outputs_dir))
    metadata.setdefault("cwd", spec.runtime.cwd or str(run_path))

    if spec.runtime.runtime is AgentRuntimeKind.PYTHON:
        metadata["entrypoint"] = spec.runtime.entrypoint
    elif spec.runtime.runtime is AgentRuntimeKind.COMMAND:
        metadata.setdefault("command", [spec.runtime.entrypoint])

    timeout_s = node.timeout_s if node.timeout_s is not None else spec.runtime.timeout_s
    return ExecutionRequest(
        run_id=run_path.name,
        node_id=node.node_id,
        agent_id=node.agent_id,
        operation=node.operation,
        runtime=spec.runtime.runtime,
        inputs=list(node.inputs),
        timeout_s=timeout_s,
        policy_snapshot=spec.operations_policy.model_dump(mode="json"),
        metadata=metadata,
    )


def _load_control_plan(run_path: Path) -> ControlPlan:
    path = run_path / "control" / "plan.json"
    if not path.exists():
        raise FileNotFoundError(f"Control plan not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    return ControlPlan.model_validate(payload)


def _load_registry_snapshot(run_path: Path) -> AgentRegistry:
    path = run_path / "control" / "registry.json"
    if not path.exists():
        raise FileNotFoundError(f"Registry snapshot not found: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    agents_raw = payload.get("agents")
    if not isinstance(agents_raw, list):
        raise ValueError("Invalid registry snapshot: 'agents' must be a list.")

    agents_by_id: dict[str, AgentSpec] = {}
    for item in agents_raw:
        spec = AgentSpec.model_validate(item)
        if spec.agent_id in agents_by_id:
            raise ValueError(f"Duplicate agent_id in registry snapshot: {spec.agent_id}")
        agents_by_id[spec.agent_id] = spec

    capability_index_raw = payload.get("capability_index", {})
    capability_index: dict[str, tuple[str, ...]] = {}
    if isinstance(capability_index_raw, dict):
        for capability, agent_ids in capability_index_raw.items():
            if not isinstance(capability, str):
                raise ValueError("Invalid registry snapshot: capability index keys must be strings.")
            if not isinstance(agent_ids, list) or not all(isinstance(item, str) for item in agent_ids):
                raise ValueError(
                    "Invalid registry snapshot: capability index values must be string lists."
                )
            capability_index[capability] = tuple(agent_ids)

    return AgentRegistry(
        agents_by_id=dict(sorted(agents_by_id.items())),
        capability_index=capability_index,
    )


def _persist_runtime_state(
    run_path: Path,
    *,
    plan: ControlPlan,
    node_states: Mapping[str, ControlNodeState],
) -> Path:
    payload = {
        "schema_version": 1,
        "plan_id": plan.plan_id,
        "node_states": {node_id: node_states[node_id].value for node_id in sorted(node_states)},
    }
    state_path = run_path / "control" / "runtime_state.json"
    _write_json_atomic(state_path, payload)
    return state_path


def _write_json_atomic(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)
