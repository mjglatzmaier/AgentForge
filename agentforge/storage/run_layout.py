from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RunLayout:
    run_dir: Path
    run_yaml: Path
    manifest_json: Path
    steps_dir: Path


def create_run_layout(base_dir: str | Path, run_id: str) -> RunLayout:
    base_path = Path(base_dir)
    run_dir = base_path / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)

    run_yaml = run_dir / "run.yaml"
    manifest_json = run_dir / "manifest.json"
    steps_dir = run_dir / "steps"

    run_yaml.touch(exist_ok=True)
    manifest_json.touch(exist_ok=True)
    steps_dir.mkdir(exist_ok=True)

    return RunLayout(
        run_dir=run_dir,
        run_yaml=run_yaml,
        manifest_json=manifest_json,
        steps_dir=steps_dir,
    )


def create_step_dir(layout: RunLayout, step_index: int, step_id: str) -> Path:
    if step_index < 0:
        raise ValueError("step_index must be >= 0")
    if not step_id.strip():
        raise ValueError("step_id must be non-empty")

    step_dir = layout.steps_dir / f"{step_index:02d}_{step_id}"
    outputs_dir = step_dir / "outputs"
    logs_dir = step_dir / "logs"
    meta_json = step_dir / "meta.json"

    outputs_dir.mkdir(parents=True, exist_ok=True)
    logs_dir.mkdir(exist_ok=True)
    meta_json.touch(exist_ok=True)

    return step_dir
