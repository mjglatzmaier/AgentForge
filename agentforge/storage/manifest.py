from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from agentforge.contracts.models import ArtifactRef, Manifest


def init_manifest(path: str | Path, run_id: str) -> Manifest:
    """
    Create a new manifest file at `path` with a valid JSON body.
    Overwrites existing file only if it is empty/whitespace.
    """
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
    """
    Load an existing manifest. Raises if missing or invalid JSON.
    This is intentionally strict: the orchestrator/run creation should call init_manifest().
    """
    manifest_path = Path(path)
    text = manifest_path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Manifest file is empty: {manifest_path}. Call init_manifest() first.")
    return Manifest.model_validate_json(text)


def save_manifest(path: str | Path, manifest: Manifest) -> None:
    """
    Atomically write manifest JSON.
    """
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = manifest_path.with_suffix(f"{manifest_path.suffix}.tmp")

    # Keep indent for readability; deterministic ordering is handled by json libs / hashing separately.
    temp_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    temp_path.replace(manifest_path)


def register_artifact(manifest: Manifest, artifact: ArtifactRef) -> None:
    """
    Register a new artifact. Enforces uniqueness by (producer_step_id, name).
    """
    if lookup_artifact(manifest, artifact.producer_step_id, artifact.name) is not None:
        raise ValueError(
            f"Artifact already registered: ({artifact.producer_step_id}, {artifact.name})"
        )
    manifest.artifacts.append(artifact)


def register_artifacts(manifest: Manifest, artifacts: Iterable[ArtifactRef]) -> None:
    """
    Bulk register artifacts. If any duplicates exist within the incoming set or against
    the manifest, raises with a helpful error.
    """
    for artifact in artifacts:
        register_artifact(manifest, artifact)


def lookup_artifact(manifest: Manifest, producer_step_id: str, name: str) -> ArtifactRef | None:
    """
    Lookup by compound key (producer_step_id, name).
    """
    for artifact in manifest.artifacts:
        if artifact.producer_step_id == producer_step_id and artifact.name == name:
            return artifact
    return None


def require_artifact(manifest: Manifest, producer_step_id: str, name: str) -> ArtifactRef:
    """
    Strict lookup by compound key (producer_step_id, name).
    """
    artifact = lookup_artifact(manifest, producer_step_id, name)
    if artifact is None:
        raise KeyError(f"Artifact not found: ({producer_step_id}, {name})")
    return artifact


def lookup_latest_by_name(manifest: Manifest, name: str) -> ArtifactRef | None:
    """
    Convenience: if you commonly refer to logical artifacts like 'docs_ranked'
    and expect only one per run, or want the latest occurrence.
    Returns the last registered artifact matching `name`.
    """
    for artifact in reversed(manifest.artifacts):
        if artifact.name == name:
            return artifact
    return None