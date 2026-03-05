from __future__ import annotations

from pathlib import Path

from agentforge.sidecar.agentctl.approvals_cli import approve, approvals_list, deny
from agentforge.sidecar.agentd.api.approvals_api import approve_approval, deny_approval, get_approvals
from agentforge.sidecar.agentd.approvals.store_v1 import ApprovalGatewayV1
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

    first = gateway.request(_request())
    second = gateway.request(_request().model_copy(update={"request_id": "req_approval_2"}))
    pending = get_approvals(runs_root).approvals
    assert {item.approval_id for item in pending} == {first.approval_id, second.approval_id}

    approved = approve_approval(runs_root, first.approval_id)
    assert approved.status is ApprovalStatus.APPROVED

    denied = deny_approval(runs_root, second.approval_id)
    assert denied.status is ApprovalStatus.DENIED
    assert get_approvals(runs_root).approvals == []


def test_approval_cli_helpers(tmp_path: Path) -> None:
    runs_root = tmp_path / "runs"
    gateway = ApprovalGatewayV1(runs_root)
    pending = gateway.request(_request())
    assert [item.approval_id for item in approvals_list(runs_root)] == [pending.approval_id]
    assert approve(runs_root, pending.approval_id).status is ApprovalStatus.APPROVED

    another = gateway.request(_request().model_copy(update={"request_id": "req_approval_3"}))
    assert deny(runs_root, another.approval_id).status is ApprovalStatus.DENIED
