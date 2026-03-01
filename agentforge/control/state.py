"""Control-plane artifact persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from typing import Mapping

from agentforge.contracts.models import ControlNodeState, ControlPlan, TriggerSpec


def persist_control_artifacts(
    run_dir: str | Path,
    *,
    plan: ControlPlan,
    trigger: TriggerSpec,
    registry: dict[str, Any],
    snapshot: dict[str, Any] | None = None,
) -> dict[str, Path]:
    """Persist control-plane JSON artifacts under runs/<run_id>/control/."""

    control_dir = Path(run_dir) / "control"
    control_dir.mkdir(parents=True, exist_ok=True)

    plan_path = control_dir / "plan.json"
    trigger_path = control_dir / "trigger.json"
    registry_path = control_dir / "registry.json"

    _write_json_atomic(plan_path, plan.model_dump(mode="json"))
    _write_json_atomic(trigger_path, trigger.model_dump(mode="json"))
    _write_json_atomic(registry_path, registry)

    written: dict[str, Path] = {
        "plan": plan_path,
        "trigger": trigger_path,
        "registry": registry_path,
    }

    if snapshot is not None:
        snapshot_path = control_dir / "snapshot.json"
        _write_json_atomic(snapshot_path, snapshot)
        written["snapshot"] = snapshot_path

    return written


def persist_final_control_snapshot(
    run_dir: str | Path,
    *,
    plan: ControlPlan,
    node_states: Mapping[str, ControlNodeState],
    last_event_id: str | None = None,
) -> Path:
    """Persist final scheduler/control snapshot to runs/<run_id>/control/snapshot.json."""

    expected_node_ids = {node.node_id for node in plan.nodes}
    provided_node_ids = set(node_states.keys())
    unknown = sorted(provided_node_ids - expected_node_ids)
    if unknown:
        raise ValueError(f"Final snapshot includes unknown node_id(s): {unknown}")
    missing = sorted(expected_node_ids - provided_node_ids)
    if missing:
        raise ValueError(f"Final snapshot missing node_id(s): {missing}")

    normalized_states = {node_id: node_states[node_id].value for node_id in sorted(node_states)}
    summary: dict[str, int] = {}
    for state in node_states.values():
        summary[state.value] = summary.get(state.value, 0) + 1

    payload: dict[str, Any] = {
        "schema_version": 1,
        "plan_id": plan.plan_id,
        "node_states": normalized_states,
        "summary": summary,
    }
    if last_event_id is not None:
        payload["last_event_id"] = last_event_id

    snapshot_path = Path(run_dir) / "control" / "snapshot.json"
    _write_json_atomic(snapshot_path, payload)
    return snapshot_path


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(path)
