from pathlib import Path

from agentforge.storage.run_layout import create_run_layout, create_step_dir


def test_create_run_layout_creates_expected_structure(tmp_path: Path) -> None:
    layout = create_run_layout(tmp_path, "run-001")

    assert layout.run_dir == tmp_path / "runs" / "run-001"
    assert layout.run_dir.is_dir()
    assert layout.run_yaml == layout.run_dir / "run.yaml"
    assert layout.run_yaml.is_file()
    assert layout.manifest_json == layout.run_dir / "manifest.json"
    assert layout.manifest_json.is_file()
    assert layout.steps_dir == layout.run_dir / "steps"
    assert layout.steps_dir.is_dir()


def test_create_step_dir_uses_zero_padded_step_name(tmp_path: Path) -> None:
    layout = create_run_layout(tmp_path, "run-002")

    step_dir = create_step_dir(layout, 0, "fetch_arxiv")

    assert step_dir.name == "00_fetch_arxiv"
    assert step_dir.is_dir()
    assert (step_dir / "outputs").is_dir()
    assert (step_dir / "logs").is_dir()
    assert (step_dir / "meta.json").is_file()
