"""Minimal v1 tool call and tool-spec envelopes for side-car implementation."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


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


class ToolOperationSpecV1(BaseModel):
    op_id: str
    required_capabilities: list[str] = Field(default_factory=list)
    approval_required: bool = False
    input_schema: dict[str, str] = Field(default_factory=dict)
    output_schema: dict[str, str] = Field(default_factory=dict)
    timeout_s: float = 30.0
    max_retries: int = 0

    @field_validator("op_id")
    @classmethod
    def validate_op_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ToolOperationSpecV1 op_id must be non-empty.")
        return normalized

    @field_validator("required_capabilities")
    @classmethod
    def validate_required_capabilities(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            item_norm = item.strip()
            if not item_norm:
                raise ValueError("required_capabilities entries must be non-empty.")
            normalized.append(item_norm)
        return normalized

    @field_validator("timeout_s")
    @classmethod
    def validate_timeout(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_s must be > 0.")
        return value

    @field_validator("max_retries")
    @classmethod
    def validate_retries(cls, value: int) -> int:
        if value < 0:
            raise ValueError("max_retries must be >= 0.")
        return value


class ToolSpecV1(BaseModel):
    name: str
    version: str
    operations: list[ToolOperationSpecV1] = Field(default_factory=list)

    @field_validator("name", "version")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("ToolSpecV1 required string fields must be non-empty.")
        return normalized

    def operation_by_id(self, op_id: str) -> ToolOperationSpecV1 | None:
        for operation in self.operations:
            if operation.op_id == op_id:
                return operation
        return None
