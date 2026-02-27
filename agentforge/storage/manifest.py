"""Manifest persistence and artifact index helpers.

Artifact identity is global by `name` within one run; `producer_step_id` is
metadata only. `manifest.json` is expected to be valid JSON whenever present;
empty files are treated as an initialization error.
"""

from __future__ import annotations

import re
from pathlib import PurePosixPath
from pathlib import Path
from typing import Iterable

from agentforge.contracts.models import ArtifactRef, Manifest

_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def init_manifest(path: str | Path, run_id: str) -> Manifest:
    """Create or load the run manifest, guaranteeing valid JSON on disk."""
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    if manifest_path.exists():
        text = manifest_path.read_text(encoding="utf-8")
        if text.strip():
            # Already initialized
            return Manifest.model_validate_json(text)

    manifest = Manifest(run_id=run_id)
    save_manifest(manifest_path, manifest)
    return manifest


def load_manifest(path: str | Path) -> Manifest:
    """Load an initialized manifest; raise if file is empty or invalid JSON."""
    manifest_path = Path(path)
    text = manifest_path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Manifest file is empty: {manifest_path}. Call init_manifest() first.")
    return Manifest.model_validate_json(text)


def save_manifest(path: str | Path, manifest: Manifest) -> None:
    """Atomically persist manifest JSON using a temp-file replace."""
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = manifest_path.with_suffix(f"{manifest_path.suffix}.tmp")

    # Keep human-readable formatting; hashing determinism is handled elsewhere.
    temp_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    temp_path.replace(manifest_path)


def register_artifact(manifest: Manifest, artifact: ArtifactRef) -> None:
    """Register one artifact; reject duplicate logical names and bad paths."""
    if lookup_artifact(manifest, artifact.name) is not None:
        raise ValueError(f"Artifact already registered: {artifact.name}")
    _validate_relative_run_path(artifact.path)
    manifest.artifacts.append(artifact)


def register_artifacts(manifest: Manifest, artifacts: Iterable[ArtifactRef]) -> None:
    """Bulk register artifacts with the same duplicate-key guarantees."""
    for artifact in artifacts:
        register_artifact(manifest, artifact)


def lookup_artifact(manifest: Manifest, name: str) -> ArtifactRef | None:
    """Lookup artifact by global artifact name."""
    for artifact in manifest.artifacts:
        if artifact.name == name:
            return artifact
    return None


def require_artifact(manifest: Manifest, name: str) -> ArtifactRef:
    """Strict variant of lookup_artifact that raises KeyError on miss."""
    artifact = lookup_artifact(manifest, name)
    if artifact is None:
        raise KeyError(f"Artifact not found: {name}")
    return artifact


def lookup_latest_by_name(manifest: Manifest, name: str) -> ArtifactRef | None:
    """Return artifact by logical name (legacy alias for lookup_artifact)."""
    return lookup_artifact(manifest, name)


def _validate_relative_run_path(path: str) -> None:
    if not path:
        raise ValueError("Artifact path must be non-empty")
    if path.startswith("/") or _WINDOWS_DRIVE_PREFIX.match(path):
        raise ValueError(f"Artifact path must be relative to run root: {path}")

    posix = PurePosixPath(path)
    if ".." in posix.parts:
        raise ValueError(f"Artifact path must not contain '..': {path}")
