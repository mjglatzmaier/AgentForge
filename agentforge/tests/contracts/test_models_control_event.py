from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agentforge.contracts.models import ControlEvent, ControlEventType


def test_control_event_valid_payload() -> None:
    event = ControlEvent(
        event_id="evt-1",
        timestamp_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        event_type=ControlEventType.PLAN_CREATED,
    )

    assert event.schema_version == 1
    assert event.payload == {}


def test_control_event_rejects_non_v1_schema() -> None:
    with pytest.raises(ValidationError, match="Unsupported ControlEvent schema_version"):
        ControlEvent(
            schema_version=2,
            event_id="evt-1",
            timestamp_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            event_type=ControlEventType.PLAN_CREATED,
        )


def test_control_event_rejects_empty_event_id() -> None:
    with pytest.raises(ValidationError, match="must be non-empty"):
        ControlEvent(
            event_id="   ",
            timestamp_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            event_type=ControlEventType.NODE_READY,
        )
