"""Approval CLI helpers for list/approve/deny flows."""

from __future__ import annotations

from pathlib import Path

from agentforge.sidecar.agentd.api.approvals_api import approve_approval, deny_approval, get_approvals
from agentforge.sidecar.core.contracts.approval_v1 import ApprovalRecordV1
from agentforge.sidecar.core.contracts.operator_auth_v1 import OperatorAuthContextV1


def approvals_list(runs_root: str | Path) -> list[ApprovalRecordV1]:
    return get_approvals(runs_root).approvals


def approve(runs_root: str | Path, approval_id: str) -> ApprovalRecordV1:
    return approve_approval(runs_root, approval_id, auth_context=_local_operator_context())


def deny(runs_root: str | Path, approval_id: str) -> ApprovalRecordV1:
    return deny_approval(runs_root, approval_id, auth_context=_local_operator_context())


def _local_operator_context() -> OperatorAuthContextV1:
    return OperatorAuthContextV1(operator_id="agentctl.local", scopes=["approvals:write"])
