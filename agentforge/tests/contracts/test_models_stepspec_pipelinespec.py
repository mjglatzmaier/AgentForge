import pytest
from pydantic import ValidationError

from agentforge.contracts.models import PipelineSpec, StepKind, StepSpec


def test_step_spec_defaults_are_independent() -> None:
    first = StepSpec(id="fetch", kind=StepKind.TOOL, ref="tools.fetch")
    second = StepSpec(id="rank", kind=StepKind.AGENT, ref="agents.rank")

    first.inputs.append("query")
    first.outputs.append("docs")
    first.config["top_k"] = 10

    assert second.inputs == []
    assert second.outputs == []
    assert second.config == {}


def test_pipeline_spec_rejects_duplicate_step_ids() -> None:
    with pytest.raises(ValidationError):
        PipelineSpec(
            name="research_digest",
            steps=[
                StepSpec(id="fetch", kind=StepKind.TOOL, ref="tools.fetch"),
                StepSpec(id="fetch", kind=StepKind.AGENT, ref="agents.fetch"),
            ],
        )


def test_step_spec_rejects_empty_id() -> None:
    with pytest.raises(ValidationError):
        StepSpec(id="   ", kind=StepKind.TOOL, ref="tools.fetch")
