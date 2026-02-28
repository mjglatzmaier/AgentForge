from pathlib import Path
from uuid import uuid4

from agentforge.contracts.models import Mode, StepStatus
from agentforge.orchestrator.runner import run_pipeline
from agentforge.storage.manifest import load_manifest


def _write_mode_module(tmp_path: Path, module_name: str) -> None:
    (tmp_path / f"{module_name}.py").write_text(
        """
from pathlib import Path


def render(ctx):
    step_dir = Path(ctx["step_dir"])
    output = step_dir / "outputs" / "result.txt"
    output.write_text(ctx.get("mode", "none"), encoding="utf-8")
    return {
        "outputs": [{"name": "result", "type": "text", "path": "outputs/result.txt"}],
        "metrics": {},
    }


def mode_visibility(ctx):
    step_dir = Path(ctx["step_dir"])
    output = step_dir / "outputs" / "mode.txt"
    output.write_text(ctx.get("mode", "absent"), encoding="utf-8")
    return {
        "outputs": [{"name": "mode_out", "type": "text", "path": "outputs/mode.txt"}],
        "metrics": {},
    }
""".strip(),
        encoding="utf-8",
    )


def test_prod_and_debug_produce_identical_artifacts(tmp_path: Path, monkeypatch) -> None:
    module_name = f"mode_steps_{uuid4().hex}"
    _write_mode_module(tmp_path, module_name)
    monkeypatch.syspath_prepend(str(tmp_path))

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""
name: mode_determinism_pipeline
steps:
  - id: render
    kind: tool
    ref: {module_name}:render
    outputs: [result]
""".strip(),
        encoding="utf-8",
    )

    prod_run = run_pipeline(pipeline_path, tmp_path, Mode.PROD)
    debug_run = run_pipeline(pipeline_path, tmp_path, Mode.DEBUG)

    prod_manifest = load_manifest(tmp_path / "runs" / prod_run / "manifest.json")
    debug_manifest = load_manifest(tmp_path / "runs" / debug_run / "manifest.json")
    prod_output = (
        tmp_path / "runs" / prod_run / "steps" / "00_render" / "outputs" / "result.txt"
    ).read_text(encoding="utf-8")
    debug_output = (
        tmp_path / "runs" / debug_run / "steps" / "00_render" / "outputs" / "result.txt"
    ).read_text(encoding="utf-8")

    assert [step.status for step in prod_manifest.steps] == [StepStatus.SUCCESS]
    assert [step.status for step in debug_manifest.steps] == [StepStatus.SUCCESS]
    assert prod_output == debug_output == "none"
    assert prod_manifest.artifacts[0].sha256 == debug_manifest.artifacts[0].sha256


def test_mode_not_passed_unless_explicitly_requested(tmp_path: Path, monkeypatch) -> None:
    module_name = f"mode_steps_{uuid4().hex}"
    _write_mode_module(tmp_path, module_name)
    monkeypatch.syspath_prepend(str(tmp_path))

    no_mode_path = tmp_path / "no_mode.yaml"
    no_mode_path.write_text(
        f"""
name: mode_hidden
steps:
  - id: mode_step
    kind: tool
    ref: {module_name}:mode_visibility
    outputs: [mode_out]
""".strip(),
        encoding="utf-8",
    )
    expose_mode_path = tmp_path / "expose_mode.yaml"
    expose_mode_path.write_text(
        f"""
name: mode_exposed
steps:
  - id: mode_step
    kind: tool
    ref: {module_name}:mode_visibility
    outputs: [mode_out]
    config:
      expose_mode_to_tool: true
""".strip(),
        encoding="utf-8",
    )

    hidden_run = run_pipeline(no_mode_path, tmp_path, Mode.DEBUG)
    exposed_run = run_pipeline(expose_mode_path, tmp_path, Mode.DEBUG)
    hidden_output = (
        tmp_path / "runs" / hidden_run / "steps" / "00_mode_step" / "outputs" / "mode.txt"
    ).read_text(encoding="utf-8")
    exposed_output = (
        tmp_path / "runs" / exposed_run / "steps" / "00_mode_step" / "outputs" / "mode.txt"
    ).read_text(encoding="utf-8")

    assert hidden_output == "absent"
    assert exposed_output == "debug"
