"""Operator authorization helpers for side-car mutation APIs."""

from __future__ import annotations

from pathlib import Path

from agentforge.sidecar.agentd.broker.audit_store_v1 import append_audit_event, create_audit_event
from agentforge.sidecar.core.contracts.operator_auth_v1 import OperatorAuthContextV1


class OperatorAuthorizationError(PermissionError):
    """Raised when operator auth context is missing or forbidden."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


def require_operator_scope(
    runs_root: str | Path,
    *,
    auth_context: OperatorAuthContextV1 | None,
    required_scope: str,
    action: str,
    run_id: str | None = None,
    approval_id: str | None = None,
) -> OperatorAuthContextV1:
    if auth_context is None:
        _append_authz_audit(
            runs_root,
            operator_id="unknown",
            run_id=run_id,
            decision="deny",
            reason_code="OPERATOR_UNAUTHORIZED",
            details={
                "action": action,
                "required_scope": required_scope,
                "approval_id": approval_id,
            },
        )
        raise OperatorAuthorizationError("OPERATOR_UNAUTHORIZED", "Missing operator auth context.")

    scopes = set(auth_context.scopes)
    if required_scope not in scopes:
        _append_authz_audit(
            runs_root,
            operator_id=auth_context.operator_id,
            run_id=run_id,
            decision="deny",
            reason_code="OPERATOR_FORBIDDEN",
            details={
                "action": action,
                "required_scope": required_scope,
                "approval_id": approval_id,
            },
        )
        raise OperatorAuthorizationError(
            "OPERATOR_FORBIDDEN",
            f"Operator '{auth_context.operator_id}' lacks scope '{required_scope}'.",
        )

    _append_authz_audit(
        runs_root,
        operator_id=auth_context.operator_id,
        run_id=run_id,
        decision="allow",
        reason_code="OPERATOR_AUTHORIZED",
        details={"action": action, "required_scope": required_scope, "approval_id": approval_id},
    )
    return auth_context


def _append_authz_audit(
    runs_root: str | Path,
    *,
    operator_id: str,
    run_id: str | None,
    decision: str,
    reason_code: str,
    details: dict[str, object],
) -> None:
    append_audit_event(
        runs_root,
        create_audit_event(
            actor=operator_id,
            run_id=run_id,
            decision=decision,
            reason_code=reason_code,
            details=details,
        ),
    )
