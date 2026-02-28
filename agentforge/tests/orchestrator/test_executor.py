from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import pytest

from agentforge.contracts.models import Mode, StepKind, StepSpec, StepStatus
from agentforge.orchestrator.executor import InProcExecutor, StepExecutionResult, StepExecutor
from agentforge.orchestrator.runner import run_pipeline


def _write_executor_module(tmp_path: Path, module_name: str) -> None:
    (tmp_path / f"{module_name}.py").write_text(
        """
def run(ctx):
    return {
        "outputs": [{"name": "docs", "type": "text", "path": "outputs/docs.txt"}],
        "metrics": {"count": 1},
    }
""".strip(),
        encoding="utf-8",
    )


def test_inproc_executor_executes_callable(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_name = f"exec_mod_{uuid4().hex}"
    _write_executor_module(tmp_path, module_name)
    monkeypatch.syspath_prepend(str(tmp_path))

    step = StepSpec(id="demo", kind=StepKind.TOOL, ref=f"{module_name}:run", outputs=["docs"])
    result = InProcExecutor().execute(step, {"step_dir": str(tmp_path)})

    assert isinstance(result, StepExecutionResult)
    assert result.status is StepStatus.SUCCESS
    assert result.raw_output["outputs"][0]["name"] == "docs"


def test_inproc_executor_rejects_non_dict_output() -> None:
    step = StepSpec(id="sqrt", kind=StepKind.TOOL, ref="math:sqrt")
    with pytest.raises(TypeError):
        InProcExecutor().execute(step, {})


def test_runner_uses_executor_boundary(tmp_path: Path) -> None:
    class StubExecutor(StepExecutor):
        def __init__(self) -> None:
            self.calls = 0

        def execute(self, step: StepSpec, context: dict[str, object]) -> StepExecutionResult:
            self.calls += 1
            output_path = Path(str(context["step_dir"])) / "outputs" / "stub.txt"
            output_path.write_text("stub", encoding="utf-8")
            now = datetime.now(timezone.utc)
            return StepExecutionResult(
                step_id=step.id,
                status=StepStatus.SUCCESS,
                started_at=now,
                ended_at=now,
                metrics={},
                outputs=[],
                raw_output={
                    "outputs": [{"name": "stub", "type": "text", "path": "outputs/stub.txt"}],
                    "metrics": {},
                },
            )

    pipeline_path = tmp_path / "pipeline.yaml"
    pipeline_path.write_text(
        """
name: boundary_pipeline
steps:
  - id: step1
    kind: tool
    ref: not.a.real.module:run
    outputs: [stub]
""".strip(),
        encoding="utf-8",
    )

    stub = StubExecutor()
    run_id = run_pipeline(pipeline_path, tmp_path, Mode.PROD, executor=stub)

    assert stub.calls == 1
    output_file = tmp_path / "runs" / run_id / "steps" / "00_step1" / "outputs" / "stub.txt"
    assert output_file.read_text(encoding="utf-8") == "stub"
