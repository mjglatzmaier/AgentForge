import pytest
from pydantic import ValidationError

from agentforge.contracts.models import TriggerKind, TriggerSpec


def test_trigger_spec_manual_defaults() -> None:
    trigger = TriggerSpec(kind=TriggerKind.MANUAL)

    assert trigger.schedule is None
    assert trigger.event_type is None
    assert trigger.metadata == {}


def test_trigger_spec_schedule_requires_schedule() -> None:
    with pytest.raises(ValidationError, match="schedule is required"):
        TriggerSpec(kind=TriggerKind.SCHEDULE)

    trigger = TriggerSpec(kind=TriggerKind.SCHEDULE, schedule="0 8 * * *", source="cron")
    assert trigger.schedule == "0 8 * * *"


def test_trigger_spec_event_requires_event_type() -> None:
    with pytest.raises(ValidationError, match="event_type is required"):
        TriggerSpec(kind=TriggerKind.EVENT)

    trigger = TriggerSpec(kind=TriggerKind.EVENT, event_type="webhook.received")
    assert trigger.event_type == "webhook.received"


@pytest.mark.parametrize(
    ("kind", "kwargs", "error"),
    [
        (TriggerKind.MANUAL, {"schedule": "0 8 * * *"}, "schedule is only allowed"),
        (TriggerKind.MANUAL, {"event_type": "push"}, "event_type is only allowed"),
        (TriggerKind.SCHEDULE, {"event_type": "push", "schedule": "0 8 * * *"}, "event_type is only allowed"),
        (TriggerKind.EVENT, {"schedule": "0 8 * * *", "event_type": "push"}, "schedule is only allowed"),
    ],
)
def test_trigger_spec_rejects_incompatible_fields(
    kind: TriggerKind, kwargs: dict[str, str], error: str
) -> None:
    with pytest.raises(ValidationError, match=error):
        TriggerSpec(kind=kind, **kwargs)
