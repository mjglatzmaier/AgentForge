from __future__ import annotations

import json
from pathlib import Path

from agentforge.sidecar.agentd.api.events_api import get_run_timeline
from agentforge.sidecar.agentd.api.runs_api import (
    cancel_run,
    get_run,
    get_run_graph,
    get_runs,
    pause_run,
    resume_run,
)
from agentforge.sidecar.agentd.broker.events_store import append_run_event, create_run_event
from agentforge.sidecar.core.contracts.events_v1 import RunEventType


def test_get_run_returns_safe_defaults_when_control_files_missing(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    (runs_root / "run_missing").mkdir(parents=True, exist_ok=True)

    detail = get_run(runs_root, run_id="run_missing")
    assert detail.run_id == "run_missing"
    assert detail.status == "unknown"
    assert detail.plan_id is None
    assert detail.node_states == {}
    assert detail.summary == {}

    graph = get_run_graph(runs_root, run_id="run_missing")
    assert graph.run_id == "run_missing"
    assert graph.nodes == []


def test_get_run_graph_reads_plan_and_runtime_state(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run_graph"
    control_dir = run_dir / "control"
    control_dir.mkdir(parents=True, exist_ok=True)
    (control_dir / "plan.json").write_text(
        json.dumps(
            {
                "plan_id": "plan_graph",
                "nodes": [
                    {
                        "node_id": "fetch",
                        "agent_id": "agent.fetch",
                        "operation": "fetch_and_snapshot",
                        "depends_on": [],
                    },
                    {
                        "node_id": "summarize",
                        "agent_id": "agent.summarize",
                        "operation": "synthesize_digest",
                        "depends_on": ["fetch"],
                    },
                ],
            }
        ),
        encoding="utf-8",
    )
    (control_dir / "runtime_state.json").write_text(
        json.dumps({"node_states": {"fetch": "succeeded", "summarize": "running"}}),
        encoding="utf-8",
    )

    graph = get_run_graph(runs_root, run_id="run_graph")
    assert [node.node_id for node in graph.nodes] == ["fetch", "summarize"]
    assert graph.nodes[0].state == "succeeded"
    assert graph.nodes[1].state == "running"
    assert graph.nodes[1].depends_on == ["fetch"]


def test_get_run_timeline_returns_normalized_summary_and_cursor(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run_timeline"
    first = create_run_event(
        run_id="run_timeline",
        event_type=RunEventType.TOOL_CALL_REQUESTED,
        payload={"operation": "exchange.get_ticker"},
    )
    second = create_run_event(
        run_id="run_timeline",
        event_type=RunEventType.TOOL_CALL_COMPLETED,
        payload={"status": "ok"},
    )
    append_run_event(run_dir, first)
    append_run_event(run_dir, second)

    page_1 = get_run_timeline(runs_root, run_id="run_timeline", limit=1)
    assert len(page_1.events) == 1
    assert page_1.events[0].summary == "ToolCallRequested: exchange.get_ticker"
    assert page_1.next_cursor == page_1.events[0].event_id

    page_2 = get_run_timeline(runs_root, run_id="run_timeline", after=page_1.next_cursor, limit=1)
    assert len(page_2.events) == 1
    assert page_2.events[0].summary == "ToolCallCompleted: ok"
    assert page_2.next_cursor is None


def test_run_control_state_transitions_are_persistent_and_idempotent(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_id = "run_control"

    paused_first = pause_run(runs_root, run_id=run_id)
    paused_second = pause_run(runs_root, run_id=run_id)
    resumed = resume_run(runs_root, run_id=run_id)
    cancelled = cancel_run(runs_root, run_id=run_id)

    assert paused_first.changed is True
    assert paused_second.changed is False
    assert resumed.changed is True
    assert cancelled.changed is True

    runs_listing = get_runs(runs_root)
    run_status = {item.run_id: item.status for item in runs_listing.runs}
    assert run_status[run_id] == "cancelled"

    detail = get_run(runs_root, run_id=run_id)
    assert detail.status == "cancelled"
