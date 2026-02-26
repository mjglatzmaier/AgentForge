import pytest

from agentforge.contracts.models import StepKind, StepSpec
from agentforge.orchestrator.runner import validate_step_outputs


def _step(*, outputs: list[str]) -> StepSpec:
    return StepSpec(id="demo", kind=StepKind.TOOL, ref="demo.module:run", outputs=outputs)


def test_validate_step_outputs_rejects_undeclared_output() -> None:
    step = _step(outputs=["docs"])

    with pytest.raises(ValueError, match="undeclared outputs"):
        validate_step_outputs(
            step,
            {
                "outputs": [
                    {"name": "docs", "type": "json", "path": "outputs/docs.json"},
                    {"name": "extra", "type": "json", "path": "outputs/extra.json"},
                ]
            },
        )


def test_validate_step_outputs_rejects_missing_output() -> None:
    step = _step(outputs=["docs", "summary"])

    with pytest.raises(ValueError, match="missing outputs"):
        validate_step_outputs(
            step,
            {"outputs": [{"name": "docs", "type": "json", "path": "outputs/docs.json"}]},
        )


def test_validate_step_outputs_accepts_exact_match() -> None:
    step = _step(outputs=["docs", "summary"])

    validate_step_outputs(
        step,
        {
            "outputs": [
                {"name": "docs", "type": "json", "path": "outputs/docs.json"},
                {"name": "summary", "type": "json", "path": "outputs/summary.json"},
            ]
        },
    )


def test_validate_step_outputs_allows_empty_only_when_declared_empty() -> None:
    step = _step(outputs=[])
    validate_step_outputs(step, {"outputs": []})
