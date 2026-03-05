"""Artifact browse API adapters for side-car workbench clients."""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from agentforge.storage.manifest import load_manifest


class ArtifactViewV1(BaseModel):
    artifact_id: str
    name: str
    type: str
    path: str
    local_path: str
    producer_step_id: str


class RunArtifactsV1(BaseModel):
    artifacts: list[ArtifactViewV1] = Field(default_factory=list)


def get_run_artifacts(runs_root: str | Path, *, run_id: str) -> RunArtifactsV1:
    """Adapter for GET /runs/{run_id}/artifacts."""

    run_dir = Path(runs_root) / run_id
    manifest_path = run_dir / "manifest.json"
    if not manifest_path.exists():
        return RunArtifactsV1()
    manifest = load_manifest(manifest_path)
    artifacts: list[ArtifactViewV1] = []
    for index, artifact in enumerate(manifest.artifacts):
        local_path = _safe_local_artifact_path(run_dir, artifact.path)
        artifacts.append(
            ArtifactViewV1(
                artifact_id=f"art-{index:04d}",
                name=artifact.name,
                type=artifact.type,
                path=artifact.path,
                local_path=str(local_path),
                producer_step_id=artifact.producer_step_id,
            )
        )
    return RunArtifactsV1(artifacts=artifacts)


def get_run_artifact_by_id(
    runs_root: str | Path,
    *,
    run_id: str,
    artifact_id: str,
) -> ArtifactViewV1:
    """Adapter for GET /runs/{run_id}/artifacts/{artifact_id}."""

    listing = get_run_artifacts(runs_root, run_id=run_id)
    for artifact in listing.artifacts:
        if artifact.artifact_id == artifact_id:
            return artifact
    raise KeyError(f"Artifact not found for run '{run_id}': {artifact_id}")


def _safe_local_artifact_path(run_dir: Path, relative_path: str) -> Path:
    resolved = (run_dir / relative_path).resolve()
    run_root = run_dir.resolve()
    try:
        resolved.relative_to(run_root)
    except ValueError as exc:
        raise ValueError(f"Artifact path escapes run directory: {relative_path}") from exc
    return resolved

