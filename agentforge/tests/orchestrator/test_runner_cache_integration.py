import json
from pathlib import Path
from uuid import uuid4

from agentforge.contracts.models import Mode, StepStatus
from agentforge.orchestrator.runner import run_pipeline
from agentforge.storage.manifest import load_manifest


def _write_cache_step_module(tmp_path: Path, module_name: str) -> None:
    (tmp_path / f"{module_name}.py").write_text(
        """
from pathlib import Path


def produce(ctx):
    counter_path = Path(ctx["config"]["counter_file"])
    current = int(counter_path.read_text(encoding="utf-8")) if counter_path.exists() else 0
    current += 1
    counter_path.write_text(str(current), encoding="utf-8")

    output_path = Path(ctx["step_dir"]) / "outputs" / "value.txt"
    output_path.write_text(f"value-{current}", encoding="utf-8")
    return {
        "outputs": [{"name": "value", "type": "text", "path": "outputs/value.txt"}],
        "metrics": {"count": current},
    }
""".strip(),
        encoding="utf-8",
    )


def test_running_pipeline_twice_reuses_cached_outputs(
    tmp_path: Path, monkeypatch
) -> None:
    module_name = f"cache_steps_{uuid4().hex}"
    _write_cache_step_module(tmp_path, module_name)
    monkeypatch.syspath_prepend(str(tmp_path))

    counter_file = tmp_path / "counter.txt"
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""
name: cache_pipeline
steps:
  - id: produce
    kind: tool
    ref: {module_name}:produce
    outputs: [value]
    config:
      counter_file: "{counter_file.as_posix()}"
""".strip(),
        encoding="utf-8",
    )

    run_one = run_pipeline(pipeline_path, tmp_path, Mode.PROD)
    run_two = run_pipeline(pipeline_path, tmp_path, Mode.PROD)

    run_one_output = (
        tmp_path / "runs" / run_one / "steps" / "00_produce" / "outputs" / "value.txt"
    ).read_text(encoding="utf-8")
    run_two_output = (
        tmp_path / "runs" / run_two / "steps" / "00_produce" / "outputs" / "value.txt"
    ).read_text(encoding="utf-8")
    manifest_two = load_manifest(tmp_path / "runs" / run_two / "manifest.json")

    assert run_one_output == "value-1"
    assert run_two_output == "value-1"
    assert counter_file.read_text(encoding="utf-8") == "1"
    assert [step.status for step in manifest_two.steps] == [StepStatus.SKIPPED]


def test_corrupted_cache_triggers_reexecution(tmp_path: Path, monkeypatch) -> None:
    module_name = f"cache_steps_{uuid4().hex}"
    _write_cache_step_module(tmp_path, module_name)
    monkeypatch.syspath_prepend(str(tmp_path))

    counter_file = tmp_path / "counter.txt"
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""
name: cache_pipeline
steps:
  - id: produce
    kind: tool
    ref: {module_name}:produce
    outputs: [value]
    config:
      counter_file: "{counter_file.as_posix()}"
""".strip(),
        encoding="utf-8",
    )

    _ = run_pipeline(pipeline_path, tmp_path, Mode.PROD)

    cache_records = list((tmp_path / "runs" / ".cache" / "cache_pipeline").glob("*.json"))
    assert len(cache_records) == 1
    record = json.loads(cache_records[0].read_text(encoding="utf-8"))
    cached_output_rel = record["outputs"][0]["path"]
    cached_output = tmp_path / cached_output_rel
    cached_output.write_text("corrupted", encoding="utf-8")

    run_two = run_pipeline(pipeline_path, tmp_path, Mode.PROD)
    manifest_two = load_manifest(tmp_path / "runs" / run_two / "manifest.json")
    run_two_output = (
        tmp_path / "runs" / run_two / "steps" / "00_produce" / "outputs" / "value.txt"
    ).read_text(encoding="utf-8")

    assert counter_file.read_text(encoding="utf-8") == "2"
    assert [step.status for step in manifest_two.steps] == [StepStatus.SUCCESS]
    assert run_two_output == "value-2"


def test_corrupted_cache_record_triggers_reexecution(tmp_path: Path, monkeypatch) -> None:
    module_name = f"cache_steps_{uuid4().hex}"
    _write_cache_step_module(tmp_path, module_name)
    monkeypatch.syspath_prepend(str(tmp_path))

    counter_file = tmp_path / "counter.txt"
    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        f"""
name: cache_pipeline
steps:
  - id: produce
    kind: tool
    ref: {module_name}:produce
    outputs: [value]
    config:
      counter_file: "{counter_file.as_posix()}"
""".strip(),
        encoding="utf-8",
    )

    _ = run_pipeline(pipeline_path, tmp_path, Mode.PROD)

    cache_records = list((tmp_path / "runs" / ".cache" / "cache_pipeline").glob("*.json"))
    assert len(cache_records) == 1
    cache_records[0].write_text("{not valid json", encoding="utf-8")

    run_two = run_pipeline(pipeline_path, tmp_path, Mode.PROD)
    manifest_two = load_manifest(tmp_path / "runs" / run_two / "manifest.json")
    run_two_output = (
        tmp_path / "runs" / run_two / "steps" / "00_produce" / "outputs" / "value.txt"
    ).read_text(encoding="utf-8")

    assert counter_file.read_text(encoding="utf-8") == "2"
    assert [step.status for step in manifest_two.steps] == [StepStatus.SUCCESS]
    assert run_two_output == "value-2"
