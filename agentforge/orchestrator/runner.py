"""Sequential pipeline runner orchestration.

Runner responsibilities include run directory creation, manifest updates, and
step execution bookkeeping without agent-specific logic coupling.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import yaml

from agentforge.contracts.models import Mode, RunConfig, StepSpec
from agentforge.orchestrator.pipeline import load_pipeline
from agentforge.storage.manifest import init_manifest
from agentforge.storage.run_layout import create_run_layout


def validate_step_outputs(step: StepSpec, returned: dict[str, Any]) -> None:
    """Validate that returned output keys match step output declarations exactly."""
    if not isinstance(returned, dict):
        raise TypeError(
            f"Step '{step.id}' must return a dict of outputs keyed by declared names."
        )

    expected = set(step.outputs)
    actual = set(returned.keys())
    missing = sorted(expected - actual)
    undeclared = sorted(actual - expected)

    if missing or undeclared:
        parts: list[str] = []
        if missing:
            parts.append(f"missing outputs: {missing}")
        if undeclared:
            parts.append(f"undeclared outputs: {undeclared}")
        detail = "; ".join(parts)
        raise ValueError(f"Step '{step.id}' output contract violation: {detail}")


def run_pipeline(pipeline_path: str | Path, base_dir: str | Path, mode: Mode) -> str:
    """Create run scaffolding for one pipeline and return generated run_id."""
    pipeline = load_pipeline(pipeline_path)
    run_id = str(uuid4())
    layout = create_run_layout(base_dir, run_id)

    run_config = RunConfig(
        run_id=run_id,
        timestamp=datetime.now(timezone.utc),
        mode=mode,
        pipeline_name=pipeline.name,
    )
    layout.run_yaml.write_text(
        yaml.safe_dump(run_config.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )

    init_manifest(layout.manifest_json, run_id=run_id)
    return run_id
