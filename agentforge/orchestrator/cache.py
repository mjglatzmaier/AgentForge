"""Step output cache helpers.

Cache data is intentionally stored outside individual run directories
(for example under `runs/.cache/`) to allow reuse across runs.
"""

from __future__ import annotations

import json
from pathlib import Path

from agentforge.contracts.models import ArtifactRef, Mode, StepSpec
from agentforge.storage.hashing import sha256_json


def compute_step_cache_key(step: StepSpec, mode: Mode, input_artifacts: list[ArtifactRef]) -> str:
    """Compute a deterministic cache key for one step execution."""
    payload = {
        "step": {
            "id": step.id,
            "kind": step.kind.value,
            "ref": step.ref,
            "config": step.config,
            "inputs": step.inputs,
            "outputs": step.outputs,
        },
        "mode": mode.value,
        "input_sha256": sorted(artifact.sha256 for artifact in input_artifacts),
    }
    return sha256_json(payload)


def save_cache_record(
    base_dir: str | Path,
    pipeline_name: str,
    cache_key: str,
    outputs: list[ArtifactRef],
) -> Path:
    """Store one cache record and return its file path."""
    cache_path = _cache_record_path(base_dir, pipeline_name, cache_key)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"outputs": [artifact.model_dump(mode="json") for artifact in outputs]}
    cache_path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")
    return cache_path


def load_cache_record(
    base_dir: str | Path, pipeline_name: str, cache_key: str
) -> list[ArtifactRef] | None:
    """Load one cache record if present, otherwise return None."""
    cache_path = _cache_record_path(base_dir, pipeline_name, cache_key)
    if not cache_path.exists():
        return None

    payload = json.loads(cache_path.read_text(encoding="utf-8"))
    outputs_raw = payload.get("outputs", [])
    return [ArtifactRef.model_validate(output) for output in outputs_raw]


def _cache_record_path(base_dir: str | Path, pipeline_name: str, cache_key: str) -> Path:
    if not pipeline_name.strip():
        raise ValueError("pipeline_name must be non-empty")
    if not cache_key.strip():
        raise ValueError("cache_key must be non-empty")
    return Path(base_dir) / "runs" / ".cache" / pipeline_name / f"{cache_key}.json"
