"""Approval API adapters for side-car approval endpoints."""

from __future__ import annotations

from pathlib import Path

from agentforge.sidecar.agentd.approvals.store_v1 import ApprovalGatewayV1, list_pending_approvals
from agentforge.sidecar.core.contracts.approval_v1 import ApprovalListV1, ApprovalRecordV1


def get_approvals(runs_root: str | Path) -> ApprovalListV1:
    """Adapter for GET /approvals."""

    return list_pending_approvals(runs_root)


def approve_approval(runs_root: str | Path, approval_id: str) -> ApprovalRecordV1:
    """Adapter for POST /approvals/{approval_id}:approve."""

    gateway = ApprovalGatewayV1(Path(runs_root))
    return gateway.approve(approval_id)


def deny_approval(runs_root: str | Path, approval_id: str) -> ApprovalRecordV1:
    """Adapter for POST /approvals/{approval_id}:deny."""

    gateway = ApprovalGatewayV1(Path(runs_root))
    return gateway.deny(approval_id)

