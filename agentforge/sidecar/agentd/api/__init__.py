"""Local API adapters for workbench and operator control."""

from agentforge.sidecar.agentd.api.approvals_api import approve_approval, deny_approval, get_approvals
from agentforge.sidecar.agentd.api.artifacts_api import get_run_artifact_by_id, get_run_artifacts
from agentforge.sidecar.agentd.api.events_api import get_run_events, ws_events_stream
from agentforge.sidecar.agentd.api.runs_api import get_runs

__all__ = [
    "approve_approval",
    "deny_approval",
    "get_approvals",
    "get_run_artifact_by_id",
    "get_run_artifacts",
    "get_run_events",
    "get_runs",
    "ws_events_stream",
]
