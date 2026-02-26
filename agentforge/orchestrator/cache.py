"""Step output cache helpers.

Cache data is intentionally stored outside individual run directories
(for example under `runs/.cache/`) to allow reuse across runs.
"""

from __future__ import annotations

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
