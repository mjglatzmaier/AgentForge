"""Policy configuration models and loaders for side-car policy snapshots."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class AgentIdentityV1(BaseModel):
    """Agent identity used for policy evaluation."""

    agent_id: str
    role: str
    allowed_capabilities: list[str] = Field(default_factory=list)

    @field_validator("agent_id", "role")
    @classmethod
    def validate_required_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("AgentIdentityV1 required string fields must be non-empty.")
        return normalized

    @field_validator("allowed_capabilities")
    @classmethod
    def validate_allowed_capabilities(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            item_norm = item.strip()
            if not item_norm:
                raise ValueError("allowed_capabilities entries must be non-empty.")
            normalized.append(item_norm)
        return normalized


class OperationConstraintsV1(BaseModel):
    """Per-operation policy constraints."""

    domain_allowlist: list[str] = Field(default_factory=list)
    recipient_allowlist: list[str] = Field(default_factory=list)
    symbol_allowlist: list[str] = Field(default_factory=list)
    max_notional_usd: float | None = None

    @field_validator("domain_allowlist", "recipient_allowlist", "symbol_allowlist")
    @classmethod
    def validate_allowlists(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            item_norm = item.strip().lower()
            if not item_norm:
                raise ValueError("Constraint allowlist entries must be non-empty.")
            normalized.append(item_norm)
        return normalized

    @field_validator("max_notional_usd")
    @classmethod
    def validate_max_notional(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("max_notional_usd must be > 0.")
        return value


class AgentPolicyV1(BaseModel):
    """Per-agent policy entry."""

    role: str = "default"
    allowed_capabilities: list[str] = Field(default_factory=list)
    approval_required_ops: list[str] = Field(default_factory=list)
    rate_limits: dict[str, int] = Field(default_factory=dict)
    constraints: dict[str, OperationConstraintsV1] = Field(default_factory=dict)

    @field_validator("role")
    @classmethod
    def validate_role(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("AgentPolicyV1 role must be non-empty.")
        return normalized

    @field_validator("allowed_capabilities", "approval_required_ops")
    @classmethod
    def validate_string_lists(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            item_norm = item.strip()
            if not item_norm:
                raise ValueError("Policy list entries must be non-empty.")
            normalized.append(item_norm)
        return normalized

    @field_validator("rate_limits")
    @classmethod
    def validate_rate_limits(cls, value: dict[str, int]) -> dict[str, int]:
        normalized: dict[str, int] = {}
        for key, raw in value.items():
            key_norm = key.strip()
            if not key_norm:
                raise ValueError("rate_limits keys must be non-empty.")
            if raw < 1:
                raise ValueError("rate_limits values must be >= 1.")
            normalized[key_norm] = raw
        return normalized

    @field_validator("constraints")
    @classmethod
    def validate_constraints(
        cls,
        value: dict[str, OperationConstraintsV1],
    ) -> dict[str, OperationConstraintsV1]:
        normalized: dict[str, OperationConstraintsV1] = {}
        for key, raw in value.items():
            key_norm = key.strip()
            if not key_norm:
                raise ValueError("constraints keys must be non-empty.")
            normalized[key_norm] = raw
        return normalized


class PolicyDefaultsV1(BaseModel):
    """Global policy defaults."""

    deny_by_default: bool = True


class PolicyConfigV1(BaseModel):
    """Top-level policy snapshot."""

    policy_version: Literal[1] = 1
    policy_snapshot_id: str
    defaults: PolicyDefaultsV1 = Field(default_factory=PolicyDefaultsV1)
    agents: dict[str, AgentPolicyV1] = Field(default_factory=dict)

    @field_validator("policy_snapshot_id")
    @classmethod
    def validate_snapshot_id(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("policy_snapshot_id must be non-empty.")
        return normalized

    @field_validator("agents")
    @classmethod
    def validate_agents(cls, value: dict[str, AgentPolicyV1]) -> dict[str, AgentPolicyV1]:
        normalized: dict[str, AgentPolicyV1] = {}
        for key, policy in value.items():
            key_norm = key.strip()
            if not key_norm:
                raise ValueError("agent ids in policy must be non-empty.")
            normalized[key_norm] = policy
        return normalized


def load_policy_config(path: str | Path) -> PolicyConfigV1:
    """Load policy snapshot from YAML or JSON."""

    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Policy config not found: {file_path}")
    text = file_path.read_text(encoding="utf-8")

    suffix = file_path.suffix.lower()
    if suffix == ".json":
        payload = json.loads(text)
    elif suffix in {".yaml", ".yml"}:
        payload = yaml.safe_load(text)
    else:
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = yaml.safe_load(text)

    if not isinstance(payload, dict):
        raise ValueError("Policy config root must be a mapping.")
    return PolicyConfigV1.model_validate(payload)
