"""Event model v1 for append-only run event logs."""

from __future__ import annotations

from enum import Enum
from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class RunEventType(str, Enum):
    """Supported side-car event types for run-level audit logs."""

    RUN_STARTED = "RunStarted"
    STEP_STARTED = "StepStarted"
    TOOL_CALL_REQUESTED = "ToolCallRequested"
    APPROVAL_REQUESTED = "ApprovalRequested"
    APPROVAL_TOKEN_ISSUED = "ApprovalTokenIssued"
    APPROVAL_TOKEN_USED = "ApprovalTokenUsed"
    APPROVAL_TOKEN_EXPIRED = "ApprovalTokenExpired"
    APPROVAL_TOKEN_REJECTED = "ApprovalTokenRejected"
    TOOL_CALL_COMPLETED = "ToolCallCompleted"
    ARTIFACT_WRITTEN = "ArtifactWritten"
    STEP_COMPLETED = "StepCompleted"
    RUN_COMPLETED = "RunCompleted"
    RUN_FAILED = "RunFailed"


class RunEventV1(BaseModel):
    """Typed event envelope persisted to runs/<run_id>/events.jsonl."""

    schema_version: Literal[1] = 1
    event_id: str
    timestamp_utc: AwareDatetime
    event_type: RunEventType
    run_id: str
    step_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id", "run_id", "step_id")
    @classmethod
    def validate_non_empty_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("RunEventV1 string fields must be non-empty when provided.")
        return normalized


class RunEventsPageV1(BaseModel):
    """Paged event listing payload for GET /runs/{run_id}/events."""

    events: list[RunEventV1] = Field(default_factory=list)
    next_cursor: str | None = None
