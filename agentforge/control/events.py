"""Append-only control event log utilities."""

from __future__ import annotations

import json
from pathlib import Path

from agentforge.contracts.models import ControlEvent


def append_control_event(run_dir: str | Path, event: ControlEvent) -> Path:
    """Append one event to runs/<run_id>/control/events.jsonl."""

    log_path = _events_log_path(run_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(event.model_dump_json() + "\n")
    return log_path


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
