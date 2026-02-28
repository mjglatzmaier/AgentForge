import json
from pathlib import Path
from uuid import uuid4

import pytest

from agentforge.contracts.models import Mode, StepStatus
import agentforge.orchestrator.runner as runner_module
from agentforge.orchestrator.runner import run_pipeline
from agentforge.storage.manifest import load_manifest


def _write_module(tmp_path: Path, module_name: str) -> None:
    (tmp_path / f"{module_name}.py").write_text(
        """
from pathlib import Path


def step_one(ctx):
    run_dir = Path(ctx["run_dir"])
    step_dir = Path(ctx["step_dir"])
    output_file = step_dir / "outputs" / "docs.txt"
    output_file.write_text("docs", encoding="utf-8")
    order_file = run_dir / "order.txt"
    previous = order_file.read_text(encoding="utf-8") if order_file.exists() else ""
    order_file.write_text(previous + "step_one\\n", encoding="utf-8")
    return {
        "outputs": [{"name": "docs", "type": "text", "path": "outputs/docs.txt"}],
        "metrics": {"items": 1},
    }


def step_two(ctx):
    run_dir = Path(ctx["run_dir"])
    step_dir = Path(ctx["step_dir"])
    source = Path(ctx["inputs"]["docs"]["abs_path"]).read_text(encoding="utf-8")
    output_file = step_dir / "outputs" / "summary.txt"
    output_file.write_text(source + "-summary", encoding="utf-8")
    order_file = run_dir / "order.txt"
    previous = order_file.read_text(encoding="utf-8") if order_file.exists() else ""
    order_file.write_text(previous + "step_two\\n", encoding="utf-8")
    return {
        "outputs": [{"name": "summary", "type": "text", "path": "outputs/summary.txt"}],
        "metrics": {"items": 1},
    }


def fail_step(ctx):
    raise RuntimeError("intentional failure")


def never_run(ctx):
    step_dir = Path(ctx["step_dir"])
    marker = step_dir / "outputs" / "never.txt"
    marker.write_text("should-not-run", encoding="utf-8")
    return {
        "outputs": [{"name": "never", "type": "text", "path": "outputs/never.txt"}],
        "metrics": {},
    }
""".strip(),
        encoding="utf-8",
    )


def test_two_step_pipeline_executes_in_order_and_registers_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_name = f"fake_steps_{uuid4().hex}"
    _write_module(tmp_path, module_name)
    monkeypatch.syspath_prepend(str(tmp_path))

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""
name: exec_pipeline
steps:
  - id: one
    kind: tool
    ref: {module_name}:step_one
    outputs: [docs]
  - id: two
    kind: tool
    ref: {module_name}:step_two
    inputs: [docs]
    outputs: [summary]
""".strip(),
        encoding="utf-8",
    )

    run_id = run_pipeline(pipeline_path, tmp_path, Mode.PROD)
    run_dir = tmp_path / "runs" / run_id

    step_dirs = sorted(path.name for path in (run_dir / "steps").iterdir())
    assert step_dirs == ["00_one", "01_two"]
    assert (run_dir / "order.txt").read_text(encoding="utf-8").splitlines() == ["step_one", "step_two"]

    for step_dir in step_dirs:
        meta = json.loads((run_dir / "steps" / step_dir / "meta.json").read_text(encoding="utf-8"))
        assert {"step_id", "status", "started_at", "ended_at", "metrics", "outputs"} <= set(meta.keys())
        assert meta["status"] == StepStatus.SUCCESS.value

    manifest = load_manifest(run_dir / "manifest.json")
    assert [step.status for step in manifest.steps] == [StepStatus.SUCCESS, StepStatus.SUCCESS]
    assert [artifact.name for artifact in manifest.artifacts] == ["docs", "summary"]


def test_failure_halts_pipeline_and_writes_failed_meta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_name = f"fake_steps_{uuid4().hex}"
    _write_module(tmp_path, module_name)
    monkeypatch.syspath_prepend(str(tmp_path))

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""
name: fail_pipeline
steps:
  - id: one
    kind: tool
    ref: {module_name}:step_one
    outputs: [docs]
  - id: fail
    kind: tool
    ref: {module_name}:fail_step
    inputs: [docs]
    outputs: [broken]
  - id: three
    kind: tool
    ref: {module_name}:never_run
    outputs: [never]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Pipeline execution failed at step 'fail'"):
        run_pipeline(pipeline_path, tmp_path, Mode.DEBUG)

    run_dirs = [path for path in (tmp_path / "runs").iterdir() if path.name != ".cache"]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]

    step_dirs = sorted(path.name for path in (run_dir / "steps").iterdir())
    assert step_dirs == ["00_one", "01_fail"]

    failed_meta = json.loads((run_dir / "steps" / "01_fail" / "meta.json").read_text(encoding="utf-8"))
    assert failed_meta["status"] == StepStatus.FAILED.value
    assert "error" in failed_meta

    manifest = load_manifest(run_dir / "manifest.json")
    assert [step.status for step in manifest.steps] == [StepStatus.SUCCESS, StepStatus.FAILED]
    assert [artifact.name for artifact in manifest.artifacts] == ["docs"]


def test_sha256_mismatch_triggers_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module_name = f"fake_steps_{uuid4().hex}"
    _write_module(tmp_path, module_name)
    monkeypatch.syspath_prepend(str(tmp_path))

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""
name: mismatch_pipeline
steps:
  - id: one
    kind: tool
    ref: {module_name}:step_one
    outputs: [docs]
""".strip(),
        encoding="utf-8",
    )

    call_count = {"n": 0}

    def _fake_sha256_file(path: Path | str) -> str:
        call_count["n"] += 1
        return "good-sha" if call_count["n"] == 1 else "bad-sha"

    monkeypatch.setattr(runner_module, "sha256_file", _fake_sha256_file)

    with pytest.raises(RuntimeError, match="Pipeline execution failed at step 'one'"):
        run_pipeline(pipeline_path, tmp_path, Mode.DEBUG)

    run_dirs = [path for path in (tmp_path / "runs").iterdir() if path.name != ".cache"]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    meta = json.loads((run_dir / "steps" / "00_one" / "meta.json").read_text(encoding="utf-8"))
    assert meta["status"] == StepStatus.FAILED.value
    assert "sha256 mismatch" in meta["error"]["message"]

    manifest = load_manifest(run_dir / "manifest.json")
    assert [step.status for step in manifest.steps] == [StepStatus.FAILED]
    assert manifest.artifacts == []


def test_failed_step_is_not_cached(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = f"fake_steps_{uuid4().hex}"
    _write_module(tmp_path, module_name)
    monkeypatch.syspath_prepend(str(tmp_path))

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""
name: fail_only_pipeline
steps:
  - id: fail
    kind: tool
    ref: {module_name}:fail_step
    outputs: [broken]
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(RuntimeError, match="Pipeline execution failed at step 'fail'"):
        run_pipeline(pipeline_path, tmp_path, Mode.PROD)

    cache_dir = tmp_path / "runs" / ".cache" / "fail_only_pipeline"
    if cache_dir.exists():
        assert list(cache_dir.glob("*.json")) == []
