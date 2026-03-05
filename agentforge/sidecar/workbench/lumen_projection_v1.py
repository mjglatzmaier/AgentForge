"""Workbench projection helpers for minimal Lumen integration."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from agentforge.sidecar.agentd.api.approvals_api import get_approvals
from agentforge.sidecar.agentd.api.artifacts_api import get_run_artifacts
from agentforge.sidecar.agentd.api.events_api import get_run_events
from agentforge.sidecar.agentd.api.runs_api import get_runs
from agentforge.sidecar.core.contracts.approval_v1 import ApprovalRecordV1
from agentforge.sidecar.core.contracts.events_v1 import RunEventV1


class RunsPanelModelV1(BaseModel):
    runs: list[dict[str, str]] = Field(default_factory=list)


class EventTimelineModelV1(BaseModel):
    run_id: str
    events: list[RunEventV1] = Field(default_factory=list)
    next_cursor: str | None = None


class ApprovalModalModelV1(BaseModel):
    approvals: list[ApprovalRecordV1] = Field(default_factory=list)


class ArtifactViewerModelV1(BaseModel):
    run_id: str
    artifacts: list[dict[str, str]] = Field(default_factory=list)


def build_runs_panel(runs_root: str | Path) -> RunsPanelModelV1:
    listing = get_runs(runs_root)
    return RunsPanelModelV1(
        runs=[{"run_id": item.run_id, "status": item.status} for item in listing.runs]
    )


def build_event_timeline(
    runs_root: str | Path,
    *,
    run_id: str,
    after: str | None = None,
    limit: int = 200,
) -> EventTimelineModelV1:
    page = get_run_events(runs_root, run_id=run_id, after=after, limit=limit)
    return EventTimelineModelV1(run_id=run_id, events=page.events, next_cursor=page.next_cursor)


def build_approval_modal(runs_root: str | Path) -> ApprovalModalModelV1:
    return ApprovalModalModelV1(approvals=get_approvals(runs_root).approvals)


def build_artifact_viewer(runs_root: str | Path, *, run_id: str) -> ArtifactViewerModelV1:
    listing = get_run_artifacts(runs_root, run_id=run_id)
    return ArtifactViewerModelV1(
        run_id=run_id,
        artifacts=[
            {
                "artifact_id": item.artifact_id,
                "name": item.name,
                "type": item.type,
                "path": item.path,
                "local_path": item.local_path,
            }
            for item in listing.artifacts
        ],
    )

