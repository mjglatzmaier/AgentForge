"""Control-plane artifact persistence helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from agentforge.contracts.models import ControlPlan, TriggerSpec


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


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temp_path.replace(path)
