from pathlib import Path
from uuid import UUID

import yaml

from agentforge.contracts.models import Mode, RunConfig
from agentforge.orchestrator.runner import run_pipeline
from agentforge.storage.manifest import load_manifest


def _write_pipeline(path: Path) -> None:
    path.write_text(
        """
name: skeleton_pipeline
steps: []
""".strip(),
        encoding="utf-8",
    )


def test_run_pipeline_creates_run_directory(tmp_path: Path) -> None:
    pipeline_path = tmp_path / "pipeline.yaml"
    _write_pipeline(pipeline_path)

    run_id = run_pipeline(pipeline_path, tmp_path, Mode.PROD)
    run_dir = tmp_path / "runs" / run_id

    # Validate run_id format and created layout.
    assert str(UUID(run_id)) == run_id
    assert run_dir.is_dir()
    assert (run_dir / "steps").is_dir()
    assert list((run_dir / "steps").iterdir()) == []


def test_run_pipeline_writes_valid_run_yaml(tmp_path: Path) -> None:
    pipeline_path = tmp_path / "pipeline.yaml"
    _write_pipeline(pipeline_path)

    run_id = run_pipeline(pipeline_path, tmp_path, Mode.DEBUG)
    run_yaml = tmp_path / "runs" / run_id / "run.yaml"

    assert run_yaml.is_file()
    loaded = yaml.safe_load(run_yaml.read_text(encoding="utf-8"))
    config = RunConfig.model_validate(loaded)
    assert config.run_id == run_id
    assert config.pipeline_name == "skeleton_pipeline"
    assert config.mode is Mode.DEBUG


def test_run_pipeline_initializes_manifest_with_run_id(tmp_path: Path) -> None:
    pipeline_path = tmp_path / "pipeline.yaml"
    _write_pipeline(pipeline_path)

    run_id = run_pipeline(pipeline_path, tmp_path, Mode.EVAL)
    manifest_path = tmp_path / "runs" / run_id / "manifest.json"

    assert manifest_path.is_file()
    manifest = load_manifest(manifest_path)
    assert manifest.run_id == run_id
    assert manifest.artifacts == []
    assert manifest.steps == []
