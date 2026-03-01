"""Append-only control event log utilities."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from agentforge.contracts.models import ControlEvent, ControlEventType, ControlNodeState


def append_control_event(run_dir: str | Path, event: ControlEvent) -> Path:
    """Append one event to runs/<run_id>/control/events.jsonl."""

    log_path = _events_log_path(run_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(event.model_dump_json() + "\n")
    return log_path


def append_node_transition_event(
    run_dir: str | Path,
    *,
    event_id: str,
    timestamp_utc: datetime,
    node_id: str,
    to_state: ControlNodeState,
    payload: dict[str, Any] | None = None,
) -> Path:
    """Append a typed node transition event to the control event log."""

    event_type = _event_type_for_node_state(to_state)
    transition_payload: dict[str, Any] = dict(payload or {})
    transition_payload.setdefault("state", to_state.value)
    event = ControlEvent(
        event_id=event_id,
        timestamp_utc=timestamp_utc,
        event_type=event_type,
        node_id=node_id,
        payload=transition_payload,
    )
    return append_control_event(run_dir, event)


def load_control_events(run_dir: str | Path) -> list[ControlEvent]:
    """Load and validate control events for replay."""

    log_path = _events_log_path(run_dir)
    if not log_path.exists():
        return []

    events: list[ControlEvent] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(ControlEvent.model_validate(json.loads(line)))
    return replay_control_events(events)


def replay_control_events(events: list[ControlEvent]) -> list[ControlEvent]:
    """Validate replay rules and return events in append order."""

    seen_event_ids: set[str] = set()
    for event in events:
        if event.schema_version != 1:
            raise ValueError("Unsupported ControlEvent schema_version for replay.")
        if event.event_id in seen_event_ids:
            raise ValueError(f"Duplicate ControlEvent event_id: {event.event_id}")
        seen_event_ids.add(event.event_id)
    return list(events)


def _events_log_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / "control" / "events.jsonl"


def _event_type_for_node_state(state: ControlNodeState) -> ControlEventType:
    mapping = {
        ControlNodeState.READY: ControlEventType.NODE_READY,
        ControlNodeState.RUNNING: ControlEventType.NODE_STARTED,
        ControlNodeState.SUCCEEDED: ControlEventType.NODE_SUCCEEDED,
        ControlNodeState.FAILED: ControlEventType.NODE_FAILED,
    }
    event_type = mapping.get(state)
    if event_type is None:
        raise ValueError(f"Unsupported node transition state for events: {state.value}")
    return event_type
