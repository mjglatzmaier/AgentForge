"""Approval API adapters for side-car approval endpoints."""

from __future__ import annotations

from pathlib import Path

from agentforge.sidecar.agentd.api.authz_v1 import require_operator_scope
from agentforge.sidecar.agentd.approvals.store_v1 import ApprovalGatewayV1, list_pending_approvals
from agentforge.sidecar.core.contracts.approval_v1 import ApprovalListV1, ApprovalRecordV1
from agentforge.sidecar.core.contracts.operator_auth_v1 import OperatorAuthContextV1


def get_approvals(runs_root: str | Path) -> ApprovalListV1:
    """Adapter for GET /approvals."""

    return list_pending_approvals(runs_root)


def approve_approval(
    runs_root: str | Path,
    approval_id: str,
    *,
    auth_context: OperatorAuthContextV1 | None = None,
) -> ApprovalRecordV1:
    """Adapter for POST /approvals/{approval_id}:approve."""

    gateway = ApprovalGatewayV1(Path(runs_root))
    record = gateway.get(approval_id)
    require_operator_scope(
        runs_root,
        auth_context=auth_context,
        required_scope="approvals:write",
        action="approve_approval",
        run_id=record.run_id if record is not None else None,
        approval_id=approval_id,
    )
    return gateway.approve(approval_id)


def deny_approval(
    runs_root: str | Path,
    approval_id: str,
    *,
    auth_context: OperatorAuthContextV1 | None = None,
) -> ApprovalRecordV1:
    """Adapter for POST /approvals/{approval_id}:deny."""

    gateway = ApprovalGatewayV1(Path(runs_root))
    record = gateway.get(approval_id)
    require_operator_scope(
        runs_root,
        auth_context=auth_context,
        required_scope="approvals:write",
        action="deny_approval",
        run_id=record.run_id if record is not None else None,
        approval_id=approval_id,
    )
    return gateway.deny(approval_id)
