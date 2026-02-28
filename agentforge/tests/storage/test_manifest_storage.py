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


def test_artifact_lookup_success_by_name() -> None:
    # We can work purely in-memory for this test.
    manifest = Manifest(run_id="run-001")
    
    artifact = ArtifactRef(
        name="docs_json",
        type="json",
        path="steps/00_fetch/outputs/docs.json",
        sha256="abc123",
        producer_step_id="fetch",
    )
    register_artifact(manifest, artifact)

    assert lookup_artifact(manifest, "docs_json") == artifact


def test_duplicate_artifact_name_rejected() -> None:
    manifest = Manifest(run_id="run-001")

    first = ArtifactRef(
        name="digest_md",
        type="markdown",
        path="steps/04_render/outputs/digest.md",
        sha256="def456",
        producer_step_id="render",
    )
    second = ArtifactRef(
        name="digest_md",
        type="markdown",
        path="steps/05_publish/outputs/digest_copy.md",
        sha256="xyz999",
        producer_step_id="publish",
    )
    register_artifact(manifest, first)

    with pytest.raises(ValueError):
        register_artifact(manifest, second)


def test_absolute_artifact_path_rejected() -> None:
    manifest = Manifest(run_id="run-001")

    absolute = ArtifactRef(
        name="digest",
        type="json",
        path="/tmp/digest.json",
        sha256="aaa",
        producer_step_id="fetch",
    )

    with pytest.raises(ValueError):
        register_artifact(manifest, absolute)


def test_manifest_round_trip_preserves_relative_paths(tmp_path: Path) -> None:
    layout = create_run_layout(tmp_path, "run-001")
    manifest = init_manifest(layout.manifest_json, run_id="run-001")
    artifact = ArtifactRef(
        name="output",
        type="json",
        path="steps/01_normalize/outputs/output.json",
        sha256="abc123",
        producer_step_id="normalize",
    )
    register_artifact(manifest, artifact)
    save_manifest(layout.manifest_json, manifest)
    loaded = load_manifest(layout.manifest_json)
    assert loaded.artifacts[0].path == "steps/01_normalize/outputs/output.json"
