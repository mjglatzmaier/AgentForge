"""Approval CLI helpers for list/approve/deny flows."""

from __future__ import annotations

from pathlib import Path

from agentforge.sidecar.agentd.api.approvals_api import approve_approval, deny_approval, get_approvals
from agentforge.sidecar.core.contracts.approval_v1 import ApprovalRecordV1


def approvals_list(runs_root: str | Path) -> list[ApprovalRecordV1]:
    return get_approvals(runs_root).approvals


def approve(runs_root: str | Path, approval_id: str) -> ApprovalRecordV1:
    return approve_approval(runs_root, approval_id)


def deny(runs_root: str | Path, approval_id: str) -> ApprovalRecordV1:
    return deny_approval(runs_root, approval_id)

