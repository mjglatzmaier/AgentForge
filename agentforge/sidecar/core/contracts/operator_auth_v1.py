"""Operator auth context model for side-car mutation authorization."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class OperatorAuthContextV1(BaseModel):
    schema_version: Literal[1] = 1
    operator_id: str
    scopes: list[str] = Field(default_factory=list)

    @field_validator("operator_id")
    @classmethod
    def validate_operator_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("OperatorAuthContextV1 operator_id must be non-empty.")
        return normalized

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for scope in value:
            scope_norm = scope.strip()
            if not scope_norm:
                raise ValueError("OperatorAuthContextV1 scopes entries must be non-empty.")
            normalized.append(scope_norm)
        return normalized
