"""Pipeline loading and validation entry points."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agentforge.contracts.models import PipelineSpec


def load_pipeline(path: str | Path) -> PipelineSpec:
    """Load one pipeline YAML file into a validated ``PipelineSpec``."""
    pipeline_path = Path(path)

    if not pipeline_path.exists():
        raise FileNotFoundError(f"Pipeline file not found: {pipeline_path}")

    try:
        loaded = yaml.safe_load(pipeline_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse pipeline YAML at {pipeline_path}: {exc}") from exc

    if not isinstance(loaded, dict):
        loaded_type = type(loaded).__name__
        raise ValueError(
            f"Pipeline YAML root must be a mapping at {pipeline_path}; got {loaded_type}"
        )

    _validate_pipeline_name(pipeline_path, loaded)

    try:
        return PipelineSpec.model_validate(loaded)
    except ValidationError as exc:
        raise ValueError(f"Invalid pipeline spec at {pipeline_path}: {exc}") from exc


def _validate_pipeline_name(path: Path, loaded: dict[str, Any]) -> None:
    name = loaded.get("name")
    if not isinstance(name, str) or not name.strip():
        raise ValueError(f"Pipeline name must be a non-empty string at {path}")
