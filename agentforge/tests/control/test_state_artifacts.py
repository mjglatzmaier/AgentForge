import json
from pathlib import Path

from agentforge.control.state import persist_control_artifacts
from agentforge.contracts.models import (
    ControlNode,
    ControlPlan,
    TriggerKind,
    TriggerSpec,
)


def _plan() -> ControlPlan:
    return ControlPlan(
        plan_id="plan-1",
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        nodes=[
            ControlNode(
                node_id="node-1",
                agent_id="agent.research",
                operation="pipeline",
            )
        ],
    )


def test_persist_control_artifacts_writes_required_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-001"
    paths = persist_control_artifacts(
        run_dir,
        plan=_plan(),
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        registry={"agents": []},
    )

    assert set(paths.keys()) == {"plan", "trigger", "registry"}
    assert (run_dir / "control" / "plan.json").is_file()
    assert (run_dir / "control" / "trigger.json").is_file()
    assert (run_dir / "control" / "registry.json").is_file()
    assert json.loads((run_dir / "control" / "plan.json").read_text(encoding="utf-8"))["plan_id"] == "plan-1"


def test_persist_control_artifacts_writes_optional_snapshot(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-002"
    paths = persist_control_artifacts(
        run_dir,
        plan=_plan(),
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        registry={"agents": []},
        snapshot={"last_event_id": "evt-2"},
    )

    assert "snapshot" in paths
    snapshot_payload = json.loads((run_dir / "control" / "snapshot.json").read_text(encoding="utf-8"))
    assert snapshot_payload["last_event_id"] == "evt-2"


def test_persist_control_artifacts_overwrites_without_tmp_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-003"
    persist_control_artifacts(
        run_dir,
        plan=_plan(),
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        registry={"agents": ["a"]},
    )
    persist_control_artifacts(
        run_dir,
        plan=_plan(),
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        registry={"agents": ["b"]},
    )

    payload = json.loads((run_dir / "control" / "registry.json").read_text(encoding="utf-8"))
    assert payload["agents"] == ["b"]
    assert not list((run_dir / "control").glob("*.tmp"))
