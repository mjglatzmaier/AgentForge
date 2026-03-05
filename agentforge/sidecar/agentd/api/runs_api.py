"""Run listing API adapters for side-car workbench clients."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from agentforge.sidecar.agentd.api.authz_v1 import require_operator_scope
from agentforge.sidecar.core.contracts.operator_auth_v1 import OperatorAuthContextV1


class RunSummaryV1(BaseModel):
    run_id: str
    status: str


class RunsListV1(BaseModel):
    runs: list[RunSummaryV1] = Field(default_factory=list)


class RunDetailV1(BaseModel):
    run_id: str
    status: str
    plan_id: str | None = None
    last_event_id: str | None = None
    node_states: dict[str, str] = Field(default_factory=dict)
    summary: dict[str, int] = Field(default_factory=dict)


class RunGraphNodeV1(BaseModel):
    node_id: str
    agent_id: str
    operation: str
    state: str
    depends_on: list[str] = Field(default_factory=list)


class RunGraphV1(BaseModel):
    run_id: str
    nodes: list[RunGraphNodeV1] = Field(default_factory=list)


class RunControlMutationResultV1(BaseModel):
    run_id: str
    state: Literal["running", "paused", "cancelled"]
    changed: bool


def get_runs(runs_root: str | Path) -> RunsListV1:
    """Adapter for GET /runs."""

    root = Path(runs_root)
    if not root.exists():
        return RunsListV1()

    runs: list[RunSummaryV1] = []
    for item in sorted(root.iterdir(), key=lambda entry: entry.name):
        if not item.is_dir() or item.name.startswith("_"):
            continue
        runs.append(RunSummaryV1(run_id=item.name, status=_infer_run_status(item)))
    return RunsListV1(runs=runs)


def get_run(runs_root: str | Path, *, run_id: str) -> RunDetailV1:
    """Adapter for GET /runs/{run_id}."""

    run_dir = Path(runs_root) / run_id
    snapshot = _load_json_optional(run_dir / "control" / "snapshot.json")
    runtime_state = _load_json_optional(run_dir / "control" / "runtime_state.json")
    node_states = _mapping_str_to_str(snapshot.get("node_states")) if snapshot else {}
    if not node_states and runtime_state:
        node_states = _mapping_str_to_str(runtime_state.get("node_states"))
    summary = _mapping_str_to_int(snapshot.get("summary")) if snapshot else {}
    return RunDetailV1(
        run_id=run_id,
        status=_infer_run_status(run_dir),
        plan_id=_optional_str(snapshot.get("plan_id")) if snapshot else None,
        last_event_id=_optional_str(snapshot.get("last_event_id")) if snapshot else None,
        node_states=node_states,
        summary=summary,
    )


def get_run_graph(runs_root: str | Path, *, run_id: str) -> RunGraphV1:
    """Adapter for GET /runs/{run_id}/graph."""

    run_dir = Path(runs_root) / run_id
    plan = _load_json_optional(run_dir / "control" / "plan.json")
    snapshot = _load_json_optional(run_dir / "control" / "snapshot.json")
    runtime_state = _load_json_optional(run_dir / "control" / "runtime_state.json")
    node_states = _mapping_str_to_str(snapshot.get("node_states")) if snapshot else {}
    if not node_states and runtime_state:
        node_states = _mapping_str_to_str(runtime_state.get("node_states"))

    nodes_raw = plan.get("nodes") if plan else []
    if not isinstance(nodes_raw, list):
        return RunGraphV1(run_id=run_id)

    nodes: list[RunGraphNodeV1] = []
    for item in nodes_raw:
        if not isinstance(item, dict):
            continue
        node_id = _optional_str(item.get("node_id"))
        agent_id = _optional_str(item.get("agent_id"))
        operation = _optional_str(item.get("operation"))
        if node_id is None or agent_id is None or operation is None:
            continue
        depends_on = item.get("depends_on")
        parsed_depends_on: list[str] = []
        if isinstance(depends_on, list):
            parsed_depends_on = [str(dep).strip() for dep in depends_on if str(dep).strip()]
        nodes.append(
            RunGraphNodeV1(
                node_id=node_id,
                agent_id=agent_id,
                operation=operation,
                state=node_states.get(node_id, "unknown"),
                depends_on=parsed_depends_on,
            )
        )
    return RunGraphV1(run_id=run_id, nodes=nodes)


def pause_run(
    runs_root: str | Path,
    *,
    run_id: str,
    auth_context: OperatorAuthContextV1 | None = None,
) -> RunControlMutationResultV1:
    """Adapter for POST /runs/{run_id}:pause."""

    require_operator_scope(
        runs_root,
        auth_context=auth_context,
        required_scope="runs:control",
        action="pause_run",
        run_id=run_id,
    )
    return _set_run_control_state(runs_root, run_id=run_id, state="paused")


def resume_run(
    runs_root: str | Path,
    *,
    run_id: str,
    auth_context: OperatorAuthContextV1 | None = None,
) -> RunControlMutationResultV1:
    """Adapter for POST /runs/{run_id}:resume."""

    require_operator_scope(
        runs_root,
        auth_context=auth_context,
        required_scope="runs:control",
        action="resume_run",
        run_id=run_id,
    )
    return _set_run_control_state(runs_root, run_id=run_id, state="running")


def cancel_run(
    runs_root: str | Path,
    *,
    run_id: str,
    auth_context: OperatorAuthContextV1 | None = None,
) -> RunControlMutationResultV1:
    """Adapter for POST /runs/{run_id}:cancel."""

    require_operator_scope(
        runs_root,
        auth_context=auth_context,
        required_scope="runs:control",
        action="cancel_run",
        run_id=run_id,
    )
    return _set_run_control_state(runs_root, run_id=run_id, state="cancelled")


def _infer_run_status(run_dir: Path) -> str:
    control_state = _load_json_optional(run_dir / "control" / "run_control.json")
    if control_state:
        state = _optional_str(control_state.get("state"))
        if state in {"paused", "cancelled"}:
            return state
        if state == "running":
            return "running"

    snapshot_path = run_dir / "control" / "snapshot.json"
    if snapshot_path.exists():
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        summary = payload.get("summary", {})
        if isinstance(summary, dict):
            if summary.get("failed", 0):
                return "failed"
            if summary.get("running", 0) or summary.get("ready", 0):
                return "running"
            if summary.get("succeeded", 0) and not summary.get("pending", 0):
                return "succeeded"
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        return "completed"
    return "unknown"


def _set_run_control_state(
    runs_root: str | Path,
    *,
    run_id: str,
    state: Literal["running", "paused", "cancelled"],
) -> RunControlMutationResultV1:
    run_dir = Path(runs_root) / run_id
    control_dir = run_dir / "control"
    control_dir.mkdir(parents=True, exist_ok=True)
    state_path = control_dir / "run_control.json"

    existing = _load_json_optional(state_path)
    existing_state = _optional_str(existing.get("state")) if existing else None
    changed = existing_state != state
    payload = {"schema_version": 1, "run_id": run_id, "state": state}
    temp_path = state_path.with_suffix(f"{state_path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(state_path)
    return RunControlMutationResultV1(run_id=run_id, state=state, changed=changed)


def _load_json_optional(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return None
    return payload


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized else None


def _mapping_str_to_str(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    mapped: dict[str, str] = {}
    for key, item in value.items():
        key_norm = _optional_str(key)
        item_norm = _optional_str(item)
        if key_norm is not None and item_norm is not None:
            mapped[key_norm] = item_norm
    return mapped


def _mapping_str_to_int(value: object) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    mapped: dict[str, int] = {}
    for key, item in value.items():
        key_norm = _optional_str(key)
        if key_norm is None or not isinstance(item, int):
            continue
        mapped[key_norm] = item
    return mapped
