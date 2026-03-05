"""Run listing API adapters for side-car workbench clients."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, Field


class RunSummaryV1(BaseModel):
    run_id: str
    status: str


class RunsListV1(BaseModel):
    runs: list[RunSummaryV1] = Field(default_factory=list)


def get_runs(runs_root: str | Path) -> RunsListV1:
    """Adapter for GET /runs."""

    root = Path(runs_root)
    if not root.exists():
        return RunsListV1()

    runs: list[RunSummaryV1] = []
    for item in sorted(root.iterdir(), key=lambda entry: entry.name):
        if not item.is_dir() or item.name.startswith("_"):
            continue
        runs.append(RunSummaryV1(run_id=item.name, status=_infer_run_status(item)))
    return RunsListV1(runs=runs)


def _infer_run_status(run_dir: Path) -> str:
    snapshot_path = run_dir / "control" / "snapshot.json"
    if snapshot_path.exists():
        payload = json.loads(snapshot_path.read_text(encoding="utf-8"))
        summary = payload.get("summary", {})
        if isinstance(summary, dict):
            if summary.get("failed", 0):
                return "failed"
            if summary.get("running", 0) or summary.get("ready", 0):
                return "running"
            if summary.get("succeeded", 0) and not summary.get("pending", 0):
                return "succeeded"
    manifest_path = run_dir / "manifest.json"
    if manifest_path.exists():
        return "completed"
    return "unknown"

