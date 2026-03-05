"""Append-only event log store for side-car run events."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
from uuid import uuid4

from agentforge.sidecar.core.contracts.events_v1 import RunEventType, RunEventV1, RunEventsPageV1
from agentforge.sidecar.core.redaction_v1 import redact_sensitive_data


def create_run_event(
    *,
    run_id: str,
    event_type: RunEventType,
    step_id: str | None = None,
    payload: dict[str, object] | None = None,
) -> RunEventV1:
    """Create one typed event with generated ID and UTC timestamp."""

    return RunEventV1(
        event_id=f"evt-{uuid4().hex}",
        timestamp_utc=datetime.now(timezone.utc),
        event_type=event_type,
        run_id=run_id,
        step_id=step_id,
        payload=dict(payload or {}),
    )


def append_run_event(run_dir: str | Path, event: RunEventV1) -> Path:
    """Append one event to runs/<run_id>/events.jsonl."""

    log_path = _events_log_path(run_dir)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    redacted_event = event.model_copy(update={"payload": redact_sensitive_data(event.payload)})
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(redacted_event.model_dump_json() + "\n")
    return log_path


def load_run_events(run_dir: str | Path) -> list[RunEventV1]:
    """Load all events from runs/<run_id>/events.jsonl in append order."""

    log_path = _events_log_path(run_dir)
    if not log_path.exists():
        return []
    events: list[RunEventV1] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(RunEventV1.model_validate(json.loads(line)))
    _validate_unique_event_ids(events)
    return events


def list_run_events(
    run_dir: str | Path,
    *,
    after: str | None = None,
    limit: int = 100,
) -> RunEventsPageV1:
    """Return paged events to back GET /runs/{run_id}/events."""

    if limit < 1:
        raise ValueError("list_run_events limit must be >= 1.")
    events = load_run_events(run_dir)
    start_index = _cursor_start_index(events, after=after)
    page_events = events[start_index : start_index + limit]
    has_more = start_index + limit < len(events)
    next_cursor = page_events[-1].event_id if page_events and has_more else None
    return RunEventsPageV1(events=page_events, next_cursor=next_cursor)


def stream_run_events(
    run_dir: str | Path,
    *,
    after: str | None = None,
) -> Iterator[RunEventV1]:
    """Yield ordered events for WS /events/stream adapters."""

    events = load_run_events(run_dir)
    start_index = _cursor_start_index(events, after=after)
    for event in events[start_index:]:
        yield event


def _events_log_path(run_dir: str | Path) -> Path:
    return Path(run_dir) / "events.jsonl"


def _cursor_start_index(events: list[RunEventV1], *, after: str | None) -> int:
    if after is None:
        return 0
    for index, event in enumerate(events):
        if event.event_id == after:
            return index + 1
    raise ValueError(f"Unknown event cursor: {after}")


def _validate_unique_event_ids(events: list[RunEventV1]) -> None:
    seen: set[str] = set()
    for event in events:
        if event.event_id in seen:
            raise ValueError(f"Duplicate run event_id detected: {event.event_id}")
        seen.add(event.event_id)
