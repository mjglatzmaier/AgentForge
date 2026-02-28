import pytest
from pydantic import ValidationError

from agentforge.contracts.models import ControlNode, ControlPlan, TriggerKind, TriggerSpec


def _manual_trigger() -> TriggerSpec:
    return TriggerSpec(kind=TriggerKind.MANUAL, source="cli")


def test_control_plan_accepts_valid_dependency_dag() -> None:
    plan = ControlPlan(
        plan_id="plan-1",
        max_parallel=2,
        policy_snapshot={"terminal_access": "restricted"},
        trigger=_manual_trigger(),
        nodes=[
            ControlNode(node_id="ingest"),
            ControlNode(node_id="normalize", depends_on=["ingest"]),
            ControlNode(node_id="summarize", depends_on=["normalize"]),
        ],
    )

    assert [node.node_id for node in plan.nodes] == ["ingest", "normalize", "summarize"]


def test_control_plan_rejects_duplicate_node_ids() -> None:
    with pytest.raises(ValidationError, match="must be unique"):
        ControlPlan(
            plan_id="plan-dup",
            trigger=_manual_trigger(),
            nodes=[ControlNode(node_id="a"), ControlNode(node_id="a")],
        )


def test_control_plan_rejects_unknown_dependency() -> None:
    with pytest.raises(ValidationError, match="unknown node"):
        ControlPlan(
            plan_id="plan-missing",
            trigger=_manual_trigger(),
            nodes=[ControlNode(node_id="a", depends_on=["b"])],
        )


def test_control_plan_rejects_dependency_cycle() -> None:
    with pytest.raises(ValidationError, match="contain a cycle"):
        ControlPlan(
            plan_id="plan-cycle",
            trigger=_manual_trigger(),
            nodes=[
                ControlNode(node_id="a", depends_on=["b"]),
                ControlNode(node_id="b", depends_on=["a"]),
            ],
        )


def test_control_plan_serialization_is_stable() -> None:
    kwargs = {
        "plan_id": "plan-stable",
        "max_parallel": 1,
        "policy_snapshot": {"mode": "prod"},
        "trigger": _manual_trigger(),
        "nodes": [
            ControlNode(node_id="a"),
            ControlNode(node_id="b", depends_on=["a"]),
        ],
    }
    plan_a = ControlPlan(**kwargs)
    plan_b = ControlPlan(**kwargs)

    assert plan_a.model_dump(mode="json") == plan_b.model_dump(mode="json")
    assert plan_a.model_dump_json() == plan_b.model_dump_json()
