"""Kernel port interfaces for policy, approvals, broker, and connectors."""

from __future__ import annotations

from typing import Any, Protocol

from agentforge.sidecar.core.contracts.approval_v1 import ApprovalRecordV1
from agentforge.sidecar.core.policy.decision import PolicyDecisionResult

class PolicyEngine(Protocol):
    """Decides whether a requested operation is allowed."""

    def evaluate(self, *, agent_id: str, capability: str, operation: str) -> PolicyDecisionResult: ...


class ApprovalGateway(Protocol):
    """Resolves approval decisions for gated operations."""

    def request(self, request: Any) -> ApprovalRecordV1: ...

    def get(self, approval_id: str) -> ApprovalRecordV1 | None: ...


class BrokerClient(Protocol):
    """Publishes lifecycle events and routes tool-call envelopes."""

    def publish(self, event: dict[str, Any]) -> None: ...


class ConnectorInvoker(Protocol):
    """Invokes typed connector operations."""

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]: ...
