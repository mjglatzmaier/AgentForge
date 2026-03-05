"""Minimal v1 tool call envelopes for side-car implementation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ToolCallTrace(BaseModel):
    correlation_id: str
    causation_id: str | None = None


class ToolCallRequestV1(BaseModel):
    schema_version: Literal[1] = 1
    request_id: str
    run_id: str
    node_id: str
    agent_id: str
    capability: str
    operation: str
    input: dict[str, Any] = Field(default_factory=dict)
    trace: ToolCallTrace


class ToolCallErrorV1(BaseModel):
    code: str
    message: str
    retryable: bool
    details: dict[str, Any] = Field(default_factory=dict)


class ToolCallResponseV1(BaseModel):
    schema_version: Literal[1] = 1
    request_id: str
    status: Literal["ok", "error", "denied", "approval_required", "timeout"]
    output: dict[str, Any] = Field(default_factory=dict)
    error: ToolCallErrorV1 | None = None

