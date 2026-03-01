from __future__ import annotations

import pytest

from agentforge.control.scheduler import plan_scheduler_tick
from agentforge.contracts.models import (
    ControlNode,
    ControlNodeState,
    ControlPlan,
    TriggerKind,
    TriggerSpec,
)


def _node(
    node_id: str,
    *,
    agent_id: str,
    depends_on: list[str] | None = None,
    state: ControlNodeState = ControlNodeState.PENDING,
) -> ControlNode:
    return ControlNode(
        node_id=node_id,
        agent_id=agent_id,
        operation="op",
        depends_on=list(depends_on or []),
        state=state,
    )


def _plan(nodes: list[ControlNode], *, max_parallel: int = 2) -> ControlPlan:
    return ControlPlan(
        plan_id="plan-1",
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        max_parallel=max_parallel,
        nodes=nodes,
    )


def test_scheduler_promotes_pending_nodes_to_ready_when_dependencies_succeed() -> None:
    plan = _plan(
        [
            _node("ingest", agent_id="agent.ingest", state=ControlNodeState.SUCCEEDED),
            _node("summarize", agent_id="agent.summary", depends_on=["ingest"]),
        ],
        max_parallel=1,
    )

    tick = plan_scheduler_tick(
        plan,
        node_states={"ingest": ControlNodeState.SUCCEEDED, "summarize": ControlNodeState.PENDING},
        agent_max_concurrency={"agent.summary": 1},
    )

    assert tick.node_states["summarize"] is ControlNodeState.READY
    assert tick.ready_node_ids == ("summarize",)
    assert tick.dispatch_node_ids == ("summarize",)


def test_scheduler_respects_plan_max_parallel() -> None:
    plan = _plan(
        [
            _node("a", agent_id="agent.a", state=ControlNodeState.READY),
            _node("b", agent_id="agent.b", state=ControlNodeState.READY),
            _node("c", agent_id="agent.c", state=ControlNodeState.READY),
        ],
        max_parallel=2,
    )

    tick = plan_scheduler_tick(
        plan,
        agent_max_concurrency={"agent.a": 1, "agent.b": 1, "agent.c": 1},
    )

    assert tick.dispatch_node_ids == ("a", "b")


def test_scheduler_enforces_per_agent_max_concurrency() -> None:
    plan = _plan(
        [
            _node("a1", agent_id="agent.a", state=ControlNodeState.READY),
            _node("a2", agent_id="agent.a", state=ControlNodeState.READY),
            _node("b1", agent_id="agent.b", state=ControlNodeState.READY),
        ],
        max_parallel=3,
    )

    tick = plan_scheduler_tick(
        plan,
        agent_max_concurrency={"agent.a": 1, "agent.b": 1},
    )

    assert tick.dispatch_node_ids == ("a1", "b1")


def test_scheduler_uses_node_id_tiebreak_for_ready_nodes() -> None:
    plan = _plan(
        [
            _node("node-c", agent_id="agent.c", state=ControlNodeState.READY),
            _node("node-a", agent_id="agent.a", state=ControlNodeState.READY),
            _node("node-b", agent_id="agent.b", state=ControlNodeState.READY),
        ],
        max_parallel=2,
    )

    tick = plan_scheduler_tick(
        plan,
        agent_max_concurrency={"agent.a": 1, "agent.b": 1, "agent.c": 1},
    )

    assert tick.dispatch_node_ids == ("node-a", "node-b")


def test_scheduler_rejects_unknown_node_state_input() -> None:
    plan = _plan([_node("node-a", agent_id="agent.a")], max_parallel=1)

    with pytest.raises(ValueError, match="Unknown node_id"):
        plan_scheduler_tick(plan, node_states={"missing": ControlNodeState.READY})
