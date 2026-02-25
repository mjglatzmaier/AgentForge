from pathlib import Path

import pytest

from agentforge.orchestrator.pipeline import load_pipeline


def test_load_pipeline_valid_yaml_returns_pipeline_spec(tmp_path: Path) -> None:
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        """
name: research_digest
steps:
  - id: fetch
    kind: tool
    ref: tools.fetch:run
    outputs: [docs]
""".strip(),
        encoding="utf-8",
    )

    loaded = load_pipeline(pipeline_path)

    assert loaded.name == "research_digest"
    assert [step.id for step in loaded.steps] == ["fetch"]


def test_load_pipeline_rejects_duplicate_step_ids(tmp_path: Path) -> None:
    pipeline_path = tmp_path / "dup.yaml"
    pipeline_path.write_text(
        """
name: duplicate_steps
steps:
  - id: fetch
    kind: tool
    ref: tools.fetch:run
  - id: fetch
    kind: tool
    ref: tools.fetch_again:run
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid pipeline spec") as exc_info:
        load_pipeline(pipeline_path)

    assert str(pipeline_path) in str(exc_info.value)
    assert "Step IDs must be unique" in str(exc_info.value)


def test_load_pipeline_rejects_missing_required_fields(tmp_path: Path) -> None:
    pipeline_path = tmp_path / "missing_fields.yaml"
    pipeline_path.write_text(
        """
name: missing_steps
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Invalid pipeline spec") as exc_info:
        load_pipeline(pipeline_path)

    assert str(pipeline_path) in str(exc_info.value)
    assert "steps" in str(exc_info.value)


def test_load_pipeline_rejects_non_dict_root(tmp_path: Path) -> None:
    pipeline_path = tmp_path / "not_mapping.yaml"
    pipeline_path.write_text(
        """
- id: fetch
  kind: tool
  ref: tools.fetch:run
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="root must be a mapping") as exc_info:
        load_pipeline(pipeline_path)

    assert str(pipeline_path) in str(exc_info.value)


def test_load_pipeline_rejects_missing_file_with_path() -> None:
    missing_path = Path("does_not_exist.yaml")

    with pytest.raises(FileNotFoundError, match="Pipeline file not found") as exc_info:
        load_pipeline(missing_path)

    assert str(missing_path) in str(exc_info.value)


def test_load_pipeline_rejects_yaml_parse_errors_with_path(tmp_path: Path) -> None:
    pipeline_path = tmp_path / "bad.yaml"
    pipeline_path.write_text(
        """
name: bad
steps:
  - id: fetch
    kind: tool
    ref: tools.fetch:run
    outputs: [docs
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Failed to parse pipeline YAML") as exc_info:
        load_pipeline(pipeline_path)

    assert str(pipeline_path) in str(exc_info.value)


def test_load_pipeline_rejects_empty_pipeline_name(tmp_path: Path) -> None:
    pipeline_path = tmp_path / "empty_name.yaml"
    pipeline_path.write_text(
        """
name: "   "
steps: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Pipeline name must be a non-empty string") as exc_info:
        load_pipeline(pipeline_path)

    assert str(pipeline_path) in str(exc_info.value)
