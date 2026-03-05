"""Structured audit event schema for side-car control decisions."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class AuditEventV1(BaseModel):
    schema_version: Literal[1] = 1
    event_id: str
    timestamp_utc: AwareDatetime
    actor: str
    run_id: str | None = None
    request_id: str | None = None
    decision: str
    reason_code: str
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("event_id", "actor", "decision", "reason_code")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("AuditEventV1 required string fields must be non-empty.")
        return normalized

    @field_validator("run_id", "request_id")
    @classmethod
    def validate_optional_non_empty(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("AuditEventV1 optional string fields must be non-empty when provided.")
        return normalized
