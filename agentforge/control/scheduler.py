"""Deterministic control-plane scheduler primitives."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from agentforge.contracts.models import ControlNode, ControlNodeState, ControlPlan


@dataclass(frozen=True)
class SchedulerTick:
    """Scheduler output for one deterministic planning tick."""

    node_states: dict[str, ControlNodeState]
    ready_node_ids: tuple[str, ...]
    dispatch_node_ids: tuple[str, ...]


def plan_scheduler_tick(
    plan: ControlPlan,
    *,
    node_states: Mapping[str, ControlNodeState] | None = None,
    agent_max_concurrency: Mapping[str, int] | None = None,
    retry_counts: Mapping[str, int] | None = None,
) -> SchedulerTick:
    """Compute ready and dispatchable nodes for one scheduler iteration."""

    nodes_by_id = {node.node_id: node for node in plan.nodes}
    states = _build_state_map(plan, node_states=node_states)
    _apply_transient_retries(
        nodes_by_id=nodes_by_id,
        states=states,
        retry_counts=retry_counts or {},
    )
    _promote_ready_nodes(nodes_by_id=nodes_by_id, states=states)
    ready_ids = tuple(sorted(node_id for node_id, state in states.items() if state is ControlNodeState.READY))
    dispatch_ids = tuple(
        _select_dispatch_nodes(
            plan=plan,
            nodes_by_id=nodes_by_id,
            states=states,
            agent_max_concurrency=agent_max_concurrency or {},
        )
    )
    return SchedulerTick(
        node_states=states,
        ready_node_ids=ready_ids,
        dispatch_node_ids=dispatch_ids,
    )


def _build_state_map(
    plan: ControlPlan,
    *,
    node_states: Mapping[str, ControlNodeState] | None,
) -> dict[str, ControlNodeState]:
    states = {node.node_id: node.state for node in plan.nodes}
    if node_states is None:
        return states
    for node_id, state in node_states.items():
        if node_id not in states:
            raise ValueError(f"Unknown node_id in scheduler state: {node_id}")
        states[node_id] = state
    return states


def _promote_ready_nodes(
    *,
    nodes_by_id: dict[str, ControlNode],
    states: dict[str, ControlNodeState],
) -> None:
    for node_id in sorted(nodes_by_id):
        if states[node_id] is not ControlNodeState.PENDING:
            continue
        dependencies = nodes_by_id[node_id].depends_on
        if all(states[dep] is ControlNodeState.SUCCEEDED for dep in dependencies):
            states[node_id] = ControlNodeState.READY


def _apply_transient_retries(
    *,
    nodes_by_id: dict[str, ControlNode],
    states: dict[str, ControlNodeState],
    retry_counts: Mapping[str, int],
) -> None:
    for node_id in sorted(nodes_by_id):
        if node_id in retry_counts and retry_counts[node_id] < 0:
            raise ValueError(f"retry_count for node '{node_id}' must be >= 0.")
        if states[node_id] is not ControlNodeState.FAILED:
            continue
        retry_limit = _transient_retry_limit(nodes_by_id[node_id])
        if retry_limit <= 0:
            continue
        attempts = retry_counts.get(node_id, 0)
        if attempts < retry_limit:
            states[node_id] = ControlNodeState.PENDING


def _select_dispatch_nodes(
    *,
    plan: ControlPlan,
    nodes_by_id: dict[str, ControlNode],
    states: dict[str, ControlNodeState],
    agent_max_concurrency: Mapping[str, int],
) -> list[str]:
    running_total = sum(1 for state in states.values() if state is ControlNodeState.RUNNING)
    available_slots = max(plan.max_parallel - running_total, 0)
    if available_slots == 0:
        return []

    running_by_agent = _count_running_by_agent(nodes_by_id=nodes_by_id, states=states)
    selected: list[str] = []
    selected_by_agent: dict[str, int] = {}

    ready_ids = sorted(node_id for node_id, state in states.items() if state is ControlNodeState.READY)
    for node_id in ready_ids:
        if len(selected) >= available_slots:
            break
        node = nodes_by_id[node_id]
        limit = _agent_limit(node.agent_id, agent_max_concurrency)
        current_running = running_by_agent.get(node.agent_id, 0)
        current_selected = selected_by_agent.get(node.agent_id, 0)
        if current_running + current_selected >= limit:
            continue
        selected.append(node_id)
        selected_by_agent[node.agent_id] = current_selected + 1
    return selected


def _count_running_by_agent(
    *,
    nodes_by_id: dict[str, ControlNode],
    states: dict[str, ControlNodeState],
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for node_id, state in states.items():
        if state is not ControlNodeState.RUNNING:
            continue
        agent_id = nodes_by_id[node_id].agent_id
        counts[agent_id] = counts.get(agent_id, 0) + 1
    return counts


def _agent_limit(agent_id: str, limits: Mapping[str, int]) -> int:
    limit = limits.get(agent_id, 1)
    if limit < 1:
        raise ValueError(f"max_concurrency for agent '{agent_id}' must be >= 1.")
    return limit


def _transient_retry_limit(node: ControlNode) -> int:
    if not node.retry_policy:
        return 0
    raw = node.retry_policy.get("transient_max_retries")
    if raw is None:
        return 0
    if not isinstance(raw, int) or raw < 0:
        raise ValueError(
            f"Node '{node.node_id}' retry_policy.transient_max_retries must be an integer >= 0."
        )
    return raw
