import pytest
from pydantic import TypeAdapter, ValidationError

from agentforge.contracts.models import Mode, StepKind, StepStatus


@pytest.mark.parametrize(
    ("enum_type", "raw_value", "expected"),
    [
        (Mode, "prod", Mode.PROD),
        (Mode, "debug", Mode.DEBUG),
        (Mode, "eval", Mode.EVAL),
        (StepKind, "tool", StepKind.TOOL),
        (StepKind, "agent", StepKind.AGENT),
        (StepStatus, "success", StepStatus.SUCCESS),
        (StepStatus, "failed", StepStatus.FAILED),
        (StepStatus, "skipped", StepStatus.SKIPPED),
    ],
)
def test_enum_parsing(enum_type: type[Mode | StepKind | StepStatus], raw_value: str, expected: Mode | StepKind | StepStatus) -> None:
    adapter = TypeAdapter(enum_type)
    assert adapter.validate_python(raw_value) is expected


@pytest.mark.parametrize(
    ("enum_value", "serialized"),
    [
        (Mode.PROD, "prod"),
        (StepKind.TOOL, "tool"),
        (StepStatus.SUCCESS, "success"),
    ],
)
def test_enum_json_serialization(enum_value: Mode | StepKind | StepStatus, serialized: str) -> None:
    adapter = TypeAdapter(type(enum_value))
    assert adapter.dump_python(enum_value, mode="json") == serialized
    assert adapter.dump_json(enum_value) == f'"{serialized}"'.encode()


@pytest.mark.parametrize(
    ("enum_type", "invalid"),
    [
        (Mode, "invalid-mode"),
        (StepKind, "invalid-kind"),
        (StepStatus, "invalid-status"),
    ],
)
def test_enum_validation_rejects_invalid_values(
    enum_type: type[Mode | StepKind | StepStatus], invalid: str
) -> None:
    adapter = TypeAdapter(enum_type)
    with pytest.raises(ValidationError):
        adapter.validate_python(invalid)
