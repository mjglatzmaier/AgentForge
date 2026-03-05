"""Run event API adapters for side-car GET and WS surfaces."""

from __future__ import annotations

from pathlib import Path
from typing import Iterator

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

