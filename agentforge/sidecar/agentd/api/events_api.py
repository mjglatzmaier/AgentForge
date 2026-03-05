"""Run event API adapters for side-car GET and WS surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

from pydantic import BaseModel, Field

from agentforge.sidecar.agentd.broker.events_store import list_run_events, stream_run_events
from agentforge.sidecar.core.contracts.events_v1 import RunEventV1, RunEventsPageV1


def get_run_events(
    runs_root: str | Path,
    *,
    run_id: str,
    after: str | None = None,
    limit: int = 100,
) -> RunEventsPageV1:
    """Adapter for GET /runs/{run_id}/events (paged)."""

    return list_run_events(Path(runs_root) / run_id, after=after, limit=limit)


def ws_events_stream(
    runs_root: str | Path,
    *,
    run_id: str,
    after: str | None = None,
) -> Iterator[RunEventV1]:
    """Adapter for WS /events/stream (initial stream replay)."""

    yield from stream_run_events(Path(runs_root) / run_id, after=after)


class TimelineEventV1(BaseModel):
    event_id: str
    timestamp_utc: str
    event_type: str
    summary: str
    payload: dict[str, object] = Field(default_factory=dict)


class TimelinePageV1(BaseModel):
    run_id: str
    events: list[TimelineEventV1] = Field(default_factory=list)
    next_cursor: str | None = None


def get_run_timeline(
    runs_root: str | Path,
    *,
    run_id: str,
    after: str | None = None,
    limit: int = 100,
) -> TimelinePageV1:
    """Adapter for GET /runs/{run_id}/timeline."""

    page = get_run_events(runs_root, run_id=run_id, after=after, limit=limit)
    return TimelinePageV1(
        run_id=run_id,
        events=[_to_timeline_event(event) for event in page.events],
        next_cursor=page.next_cursor,
    )


def _to_timeline_event(event: RunEventV1) -> TimelineEventV1:
    payload = dict(event.payload)
    status = payload.get("status")
    operation = payload.get("operation")
    if isinstance(status, str) and status.strip():
        summary = f"{event.event_type.value}: {status.strip()}"
    elif isinstance(operation, str) and operation.strip():
        summary = f"{event.event_type.value}: {operation.strip()}"
    else:
        summary = event.event_type.value
    return TimelineEventV1(
        event_id=event.event_id,
        timestamp_utc=event.timestamp_utc.isoformat(),
        event_type=event.event_type.value,
        summary=summary,
        payload=payload,
    )
