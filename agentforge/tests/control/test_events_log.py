from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentforge.control.events import append_control_event, load_control_events, replay_control_events
from agentforge.contracts.models import ControlEvent, ControlEventType


def _event(event_id: str, event_type: ControlEventType) -> ControlEvent:
    return ControlEvent(
        event_id=event_id,
        timestamp_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        event_type=event_type,
    )


def test_append_control_event_writes_append_only_log(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-001"
    append_control_event(run_dir, _event("evt-1", ControlEventType.PLAN_CREATED))
    append_control_event(run_dir, _event("evt-2", ControlEventType.NODE_STARTED))

    log_path = run_dir / "control" / "events.jsonl"
    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert '"event_id":"evt-1"' in lines[0]
    assert '"event_id":"evt-2"' in lines[1]


def test_load_control_events_replays_in_append_order(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run-002"
    append_control_event(run_dir, _event("evt-1", ControlEventType.PLAN_CREATED))
    append_control_event(run_dir, _event("evt-2", ControlEventType.NODE_READY))

    events = load_control_events(run_dir)
    assert [event.event_id for event in events] == ["evt-1", "evt-2"]


def test_replay_control_events_rejects_duplicate_event_ids() -> None:
    events = [
        _event("evt-1", ControlEventType.PLAN_CREATED),
        _event("evt-1", ControlEventType.NODE_STARTED),
    ]
    with pytest.raises(ValueError, match="Duplicate ControlEvent event_id"):
        replay_control_events(events)
