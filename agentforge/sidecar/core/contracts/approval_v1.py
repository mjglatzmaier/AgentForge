"""Approval model v1 for gated operations."""

from __future__ import annotations

from enum import Enum
from typing import Literal

from pydantic import AwareDatetime, BaseModel, Field, field_validator


class ApprovalStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DENIED = "denied"


class ApprovalRecordV1(BaseModel):
    schema_version: Literal[1] = 1
    approval_id: str
    request_id: str
    run_id: str
    node_id: str
    agent_id: str
    operation: str
    capability: str
    status: ApprovalStatus
    created_at_utc: AwareDatetime
    decided_at_utc: AwareDatetime | None = None
    approval_token_id: str | None = None
    approval_token_expires_at_utc: AwareDatetime | None = None

    @field_validator(
        "approval_id",
        "request_id",
        "run_id",
        "node_id",
        "agent_id",
        "operation",
        "capability",
    )
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ApprovalRecordV1 string fields must be non-empty.")
        return normalized


class ApprovalTokenStatus(str, Enum):
    ISSUED = "issued"
    USED = "used"
    EXPIRED = "expired"


class ApprovalTokenV1(BaseModel):
    schema_version: Literal[1] = 1
    token_id: str
    approval_id: str
    request_id: str
    run_id: str
    node_id: str
    agent_id: str
    operation: str
    capability: str
    status: ApprovalTokenStatus
    issued_at_utc: AwareDatetime
    expires_at_utc: AwareDatetime
    used_at_utc: AwareDatetime | None = None

    @field_validator(
        "token_id",
        "approval_id",
        "request_id",
        "run_id",
        "node_id",
        "agent_id",
        "operation",
        "capability",
    )
    @classmethod
    def validate_token_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ApprovalTokenV1 string fields must be non-empty.")
        return normalized


class ApprovalTokenValidationV1(BaseModel):
    valid: bool
    reason_code: str | None = None
    token: ApprovalTokenV1 | None = None


class ApprovalListV1(BaseModel):
    approvals: list[ApprovalRecordV1] = Field(default_factory=list)
