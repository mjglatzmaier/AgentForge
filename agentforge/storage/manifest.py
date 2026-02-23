from pathlib import Path

from agentforge.contracts.models import ArtifactRef, Manifest


def load_manifest(path: str | Path) -> Manifest:
    manifest_path = Path(path)
    return Manifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))


def save_manifest(path: str | Path, manifest: Manifest) -> None:
    manifest_path = Path(path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = manifest_path.with_suffix(f"{manifest_path.suffix}.tmp")
    temp_path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")
    temp_path.replace(manifest_path)


def register_artifact(manifest: Manifest, artifact: ArtifactRef) -> None:
    if lookup_artifact(manifest, artifact.name) is not None:
        raise ValueError(f"Artifact already registered: {artifact.name}")
    manifest.artifacts.append(artifact)


def lookup_artifact(manifest: Manifest, name: str) -> ArtifactRef | None:
    return manifest.get_artifact(name)
