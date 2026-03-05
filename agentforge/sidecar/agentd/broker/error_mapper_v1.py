"""Bounded connector error mapping for broker responses."""

from __future__ import annotations

from agentforge.sidecar.core.contracts.tool_contract_v1 import ToolCallErrorV1


def map_connector_exception(exc: Exception) -> ToolCallErrorV1:
    if isinstance(exc, PermissionError):
        return ToolCallErrorV1(
            code="POLICY_DENIED",
            message=str(exc) or "Permission denied by connector policy.",
            retryable=False,
        )
    if isinstance(exc, (ValueError, TypeError, KeyError)):
        return ToolCallErrorV1(
            code="INVALID_REQUEST",
            message=str(exc) or "Invalid connector request.",
            retryable=False,
        )
    if isinstance(exc, TimeoutError):
        return ToolCallErrorV1(
            code="CONNECTOR_TIMEOUT",
            message=str(exc) or "Connector timeout.",
            retryable=True,
        )
    return ToolCallErrorV1(
        code="UPSTREAM_ERROR",
        message=str(exc) or "Connector invocation failed.",
        retryable=True,
    )
