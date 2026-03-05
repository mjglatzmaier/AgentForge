from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentforge.sidecar.agentd.api.events_api import get_run_events, ws_events_stream
from agentforge.sidecar.agentd.broker.events_store import (
    append_run_event,
    create_run_event,
    list_run_events,
    load_run_events,
)
from agentforge.sidecar.core.contracts.events_v1 import RunEventType, RunEventV1


def test_event_schema_rejects_unknown_event_type() -> None:
    with pytest.raises(ValueError):
        RunEventV1(
            event_id="evt_1",
            timestamp_utc=datetime.now(timezone.utc),
            event_type="UnknownEvent",
            run_id="run_1",
        )


def test_event_writer_persists_append_only_jsonl(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run_001"
    first = create_run_event(run_id="run_001", event_type=RunEventType.RUN_STARTED)
    second = create_run_event(
        run_id="run_001",
        event_type=RunEventType.STEP_STARTED,
        step_id="step_fetch",
    )
    path = append_run_event(run_dir, first)
    append_run_event(run_dir, second)

    assert path == run_dir / "events.jsonl"
    loaded = load_run_events(run_dir)
    assert [event.event_id for event in loaded] == [first.event_id, second.event_id]


def test_event_listing_supports_cursor_pagination(tmp_path: Path) -> None:
    run_dir = tmp_path / "runs" / "run_002"
    events = [
        create_run_event(run_id="run_002", event_type=RunEventType.RUN_STARTED),
        create_run_event(run_id="run_002", event_type=RunEventType.TOOL_CALL_REQUESTED),
        create_run_event(run_id="run_002", event_type=RunEventType.TOOL_CALL_COMPLETED),
    ]
    for event in events:
        append_run_event(run_dir, event)

    first_page = list_run_events(run_dir, limit=2)
    assert len(first_page.events) == 2
    assert first_page.next_cursor == first_page.events[-1].event_id

    second_page = list_run_events(run_dir, after=first_page.next_cursor, limit=2)
    assert len(second_page.events) == 1
    assert second_page.events[0].event_id == events[2].event_id
    assert second_page.next_cursor is None


def test_event_api_adapters_return_paged_and_streamed_events(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    run_dir = runs_root / "run_003"
    first = create_run_event(run_id="run_003", event_type=RunEventType.RUN_STARTED)
    second = create_run_event(run_id="run_003", event_type=RunEventType.STEP_COMPLETED)
    append_run_event(run_dir, first)
    append_run_event(run_dir, second)

    page = get_run_events(runs_root, run_id="run_003", limit=1)
    assert page.events[0].event_id == first.event_id
    streamed = list(ws_events_stream(runs_root, run_id="run_003", after=first.event_id))
    assert [event.event_id for event in streamed] == [second.event_id]

