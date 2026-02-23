from pathlib import Path

import pytest

from agentforge.contracts.models import ArtifactRef, Manifest
from agentforge.storage.manifest import (
    init_manifest,
    load_manifest,
    lookup_artifact,
    register_artifact,
    save_manifest,
)
from agentforge.storage.run_layout import create_run_layout


def test_manifest_round_trip_read_write(tmp_path: Path) -> None:
    layout = create_run_layout(tmp_path, "run-001")

    # Initialize a valid manifest file (no empty file touching).
    manifest = init_manifest(layout.manifest_json, run_id="run-001")

    save_manifest(layout.manifest_json, manifest)
    loaded = load_manifest(layout.manifest_json)

    assert loaded == manifest


def test_load_manifest_rejects_empty_file(tmp_path: Path) -> None:
    layout = create_run_layout(tmp_path, "run-001")

    # Create an empty manifest file to verify strict behavior.
    layout.manifest_json.write_text("", encoding="utf-8")

    with pytest.raises(ValueError):
        load_manifest(layout.manifest_json)


def test_artifact_lookup_success_by_compound_key() -> None:
    # We can work purely in-memory for this test.
    manifest = Manifest(run_id="run-001")
    
    artifact = ArtifactRef(
        name="docs_json",
        type="json",
        path="runs/run-001/steps/00_fetch/outputs/docs.json",
        sha256="abc123",
        producer_step_id="fetch",
    )
    register_artifact(manifest, artifact)

    assert lookup_artifact(manifest, "fetch", "docs_json") == artifact


def test_duplicate_compound_key_rejected() -> None:
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


def test_same_name_different_step_allowed() -> None:
    manifest = Manifest(run_id="run-001")

    a1 = ArtifactRef(
        name="output",
        type="json",
        path="runs/run-001/steps/00_fetch/outputs/output.json",
        sha256="aaa",
        producer_step_id="fetch",
    )
    a2 = ArtifactRef(
        name="output",
        type="json",
        path="runs/run-001/steps/01_normalize/outputs/output.json",
        sha256="bbb",
        producer_step_id="normalize",
    )

    register_artifact(manifest, a1)
    register_artifact(manifest, a2)

    assert lookup_artifact(manifest, "fetch", "output") == a1
    assert lookup_artifact(manifest, "normalize", "output") == a2