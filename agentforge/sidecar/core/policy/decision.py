"""Typed policy decision result for kernel dispatch checks."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


PolicyDecision = Literal["allow", "deny", "require_approval"]


class PolicyDecisionResult(BaseModel):
    decision: PolicyDecision
    reason_code: str
    policy_snapshot_id: str

