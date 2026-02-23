from pathlib import Path

import pytest

from agentforge.contracts.models import ArtifactRef, Manifest
from agentforge.storage.manifest import (
    load_manifest,
    lookup_artifact,
    register_artifact,
    save_manifest,
)
from agentforge.storage.run_layout import create_run_layout


def test_manifest_round_trip_read_write(tmp_path: Path) -> None:
    layout = create_run_layout(tmp_path, "run-001")
    manifest = Manifest(run_id="run-001")

    save_manifest(layout.manifest_json, manifest)
    loaded = load_manifest(layout.manifest_json)

    assert loaded == manifest


def test_artifact_lookup_success() -> None:
    manifest = Manifest(run_id="run-001")
    artifact = ArtifactRef(
        name="docs_json",
        type="json",
        path="runs/run-001/steps/00_fetch/outputs/docs.json",
        sha256="abc123",
        producer_step_id="fetch",
    )
    register_artifact(manifest, artifact)

    assert lookup_artifact(manifest, "docs_json") == artifact


def test_duplicate_artifact_names_rejected() -> None:
    manifest = Manifest(run_id="run-001")
    artifact = ArtifactRef(
        name="digest_md",
        type="markdown",
        path="runs/run-001/steps/04_render/outputs/digest.md",
        sha256="def456",
        producer_step_id="render",
    )
    register_artifact(manifest, artifact)

    with pytest.raises(ValueError):
        register_artifact(manifest, artifact)
