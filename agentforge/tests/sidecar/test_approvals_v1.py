from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agentforge.sidecar.agentctl.approvals_cli import approve, approvals_list, deny
from agentforge.sidecar.agentd.api.approvals_api import approve_approval, deny_approval, get_approvals
from agentforge.sidecar.agentd.api.authz_v1 import OperatorAuthorizationError
from agentforge.sidecar.agentd.broker.audit_store_v1 import load_audit_events
from agentforge.sidecar.agentd.broker.events_store import load_run_events
from agentforge.sidecar.agentd.approvals.store_v1 import ApprovalGatewayV1
from agentforge.sidecar.core.contracts.events_v1 import RunEventType
from agentforge.sidecar.core.contracts.operator_auth_v1 import OperatorAuthContextV1
from agentforge.sidecar.core.contracts.approval_v1 import ApprovalStatus
from agentforge.sidecar.core.contracts.tool_contract_v1 import ToolCallRequestV1


def _request() -> ToolCallRequestV1:
    return ToolCallRequestV1(
        request_id="req_approval_1",
        run_id="run_approval_1",
        node_id="node_approval_1",
        agent_id="agent_approval_1",
        capability="exchange.place_order",
        operation="exchange.place_order",
        input={"symbol": "BTC-USD"},
        trace={"correlation_id": "corr_approval_1"},
    )


def test_approval_gateway_returns_stable_approval_id(tmp_path: Path) -> None:
    gateway = ApprovalGatewayV1(tmp_path / "runs")
    first = gateway.request(_request())
    second = gateway.request(_request())
    assert first.approval_id == second.approval_id
    assert len(gateway.list_pending()) == 1


def test_approval_api_list_approve_and_deny(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    gateway = ApprovalGatewayV1(runs_root)
    auth_context = OperatorAuthContextV1(operator_id="operator_1", scopes=["approvals:write"])

    first = gateway.request(_request())
    second = gateway.request(_request().model_copy(update={"request_id": "req_approval_2"}))
    pending = get_approvals(runs_root).approvals
    assert {item.approval_id for item in pending} == {first.approval_id, second.approval_id}

    approved = approve_approval(runs_root, first.approval_id, auth_context=auth_context)
    assert approved.status is ApprovalStatus.APPROVED

    denied = deny_approval(runs_root, second.approval_id, auth_context=auth_context)
    assert denied.status is ApprovalStatus.DENIED
    assert get_approvals(runs_root).approvals == []
    decisions = {event.decision for event in load_audit_events(runs_root)}
    assert "approved" in decisions
    assert "denied" in decisions


def test_approval_cli_helpers(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    gateway = ApprovalGatewayV1(runs_root)
    pending = gateway.request(_request())
    assert [item.approval_id for item in approvals_list(runs_root)] == [pending.approval_id]
    assert approve(runs_root, pending.approval_id).status is ApprovalStatus.APPROVED

    another = gateway.request(_request().model_copy(update={"request_id": "req_approval_3"}))
    assert deny(runs_root, another.approval_id).status is ApprovalStatus.DENIED


def test_approval_api_denies_missing_operator_auth_and_does_not_mutate(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    gateway = ApprovalGatewayV1(runs_root)
    pending = gateway.request(_request())

    with pytest.raises(OperatorAuthorizationError, match="Missing operator auth context."):
        approve_approval(runs_root, pending.approval_id)

    record = gateway.get(pending.approval_id)
    assert record is not None
    assert record.status is ApprovalStatus.PENDING
    denied_events = [
        event
        for event in load_audit_events(runs_root)
        if event.reason_code == "OPERATOR_UNAUTHORIZED"
    ]
    assert denied_events


class _Clock:
    def __init__(self, start: datetime) -> None:
        self.current = start

    def now(self) -> datetime:
        return self.current

    def advance(self, seconds: int) -> None:
        self.current = self.current + timedelta(seconds=seconds)


def test_approval_token_is_accepted_then_single_use(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    clock = _Clock(datetime(2025, 1, 1, tzinfo=timezone.utc))
    gateway = ApprovalGatewayV1(runs_root, token_ttl_seconds=30, now_provider=clock.now)
    request = _request()
    approval = gateway.approve(gateway.request(request).approval_id)
    assert approval.approval_token_id is not None

    token_validation = gateway.validate_token(approval.approval_token_id, request)
    assert token_validation.valid is True
    consumed = gateway.consume_token(approval.approval_token_id, request)
    assert consumed.valid is True

    reused = gateway.validate_token(approval.approval_token_id, request)
    assert reused.valid is False
    assert reused.reason_code == "APPROVAL_TOKEN_USED"


def test_approval_token_rejected_after_ttl(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    clock = _Clock(datetime(2025, 1, 1, tzinfo=timezone.utc))
    gateway = ApprovalGatewayV1(runs_root, token_ttl_seconds=5, now_provider=clock.now)
    request = _request()
    approval = gateway.approve(gateway.request(request).approval_id)
    assert approval.approval_token_id is not None

    clock.advance(6)
    expired = gateway.validate_token(approval.approval_token_id, request)
    assert expired.valid is False
    assert expired.reason_code == "APPROVAL_TOKEN_EXPIRED"


def test_approval_token_rejected_on_context_mismatch_and_logs_event(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    clock = _Clock(datetime(2025, 1, 1, tzinfo=timezone.utc))
    gateway = ApprovalGatewayV1(runs_root, token_ttl_seconds=30, now_provider=clock.now)
    request = _request()
    approval = gateway.approve(gateway.request(request).approval_id)
    assert approval.approval_token_id is not None

    mismatch_request = request.model_copy(update={"node_id": "node_other"})
    mismatch = gateway.validate_token(approval.approval_token_id, mismatch_request)
    assert mismatch.valid is False
    assert mismatch.reason_code == "APPROVAL_TOKEN_CONTEXT_MISMATCH"

    event_types = [event.event_type for event in load_run_events(runs_root / request.run_id)]
    assert RunEventType.APPROVAL_TOKEN_ISSUED in event_types
    assert RunEventType.APPROVAL_TOKEN_REJECTED in event_types
