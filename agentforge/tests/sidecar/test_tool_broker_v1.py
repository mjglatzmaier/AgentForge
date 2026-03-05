from __future__ import annotations

from pathlib import Path
from typing import Any

from agentforge.sidecar.agentd.approvals.store_v1 import ApprovalGatewayV1
from agentforge.sidecar.agentd.broker.events_store import load_run_events
from agentforge.sidecar.agentd.broker.tool_broker_v1 import ToolBrokerV1
from agentforge.sidecar.core.contracts.approval_v1 import ApprovalStatus
from agentforge.sidecar.core.contracts.events_v1 import RunEventType
from agentforge.sidecar.core.contracts.tool_contract_v1 import (
    ToolCallRequestV1,
    ToolOperationSpecV1,
    ToolSpecV1,
)
from agentforge.sidecar.core.policy import PolicyConfigV1, PolicyEngineV1


class _FakeInvoker:
    def __init__(self, responses: list[object]) -> None:
        self._responses = responses
        self.calls = 0

    def invoke(self, request: dict[str, Any]) -> dict[str, Any]:
        self.calls += 1
        response = self._responses[min(self.calls - 1, len(self._responses) - 1)]
        if isinstance(response, Exception):
            raise response
        assert isinstance(response, dict)
        return response


def _request() -> ToolCallRequestV1:
    return ToolCallRequestV1(
        request_id="req_1",
        run_id="run_1",
        node_id="node_1",
        agent_id="agent_1",
        capability="exchange.read",
        operation="exchange.get_ticker",
        input={"symbol": "BTC-USD"},
        trace={"correlation_id": "corr_1"},
    )


def _spec(*, retries: int = 0, timeout_s: float = 1.0) -> ToolSpecV1:
    return ToolSpecV1(
        name="exchange-tool",
        version="1.0.0",
        operations=[
            ToolOperationSpecV1(
                op_id="exchange.get_ticker",
                required_capabilities=["exchange.read"],
                input_schema={"symbol": "str"},
                output_schema={"price": "float"},
                timeout_s=timeout_s,
                max_retries=retries,
            )
        ],
    )


def test_tool_broker_dispatch_success_and_logs_events(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"price": 101.5}}])
    broker = ToolBrokerV1(runs_root=tmp_path / "runs", tool_spec=_spec(), connector_invoker=invoker)

    response = broker.dispatch(_request(), allowed_capabilities=["exchange.read"])
    assert response.status == "ok"
    assert response.output["price"] == 101.5
    assert invoker.calls == 1

    events = load_run_events(tmp_path / "runs" / "run_1")
    assert [event.event_type for event in events] == [
        RunEventType.TOOL_CALL_REQUESTED,
        RunEventType.TOOL_CALL_COMPLETED,
    ]
    assert events[1].payload["status"] == "ok"


def test_tool_broker_denies_missing_capability(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"price": 101.5}}])
    broker = ToolBrokerV1(runs_root=tmp_path / "runs", tool_spec=_spec(), connector_invoker=invoker)

    response = broker.dispatch(_request(), allowed_capabilities=[])
    assert response.status == "denied"
    assert response.error is not None
    assert response.error.code == "POLICY_DENIED"
    assert invoker.calls == 0


def test_tool_broker_retries_then_succeeds(tmp_path: Path) -> None:
    invoker = _FakeInvoker([RuntimeError("temporary upstream error"), {"output": {"price": 101.5}}])
    broker = ToolBrokerV1(
        runs_root=tmp_path / "runs",
        tool_spec=_spec(retries=1),
        connector_invoker=invoker,
    )

    response = broker.dispatch(_request(), allowed_capabilities=["exchange.read"])
    assert response.status == "ok"
    assert invoker.calls == 2


def test_tool_broker_rejects_bad_input_schema(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"price": 101.5}}])
    broker = ToolBrokerV1(runs_root=tmp_path / "runs", tool_spec=_spec(), connector_invoker=invoker)

    bad_request = _request().model_copy(update={"input": {"symbol": 123}})
    response = broker.dispatch(bad_request, allowed_capabilities=["exchange.read"])
    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "INVALID_REQUEST"
    assert invoker.calls == 0


def test_tool_broker_enforces_policy_denial_before_invocation(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"price": 101.5}}])
    policy = PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_deny",
            "defaults": {"deny_by_default": True},
            "agents": {
                "agent_1": {
                    "role": "reader",
                    "allowed_capabilities": ["exchange.read"],
                    "approval_required_ops": [],
                }
            },
        }
    )
    broker = ToolBrokerV1(
        runs_root=tmp_path / "runs",
        tool_spec=_spec(),
        connector_invoker=invoker,
        policy_engine=PolicyEngineV1(policy),
    )

    denied_request = _request().model_copy(update={"capability": "exchange.place_order"})
    response = broker.dispatch(denied_request)
    assert response.status == "denied"
    assert response.error is not None
    assert response.error.code == "POLICY_DENIED"
    assert invoker.calls == 0


def test_tool_broker_returns_approval_required_when_policy_demands_it(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"price": 101.5}}])
    approval_gateway = ApprovalGatewayV1(tmp_path / "runs")
    policy = PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_approval",
            "defaults": {"deny_by_default": True},
            "agents": {
                "agent_1": {
                    "role": "trader",
                    "allowed_capabilities": ["exchange.read"],
                    "approval_required_ops": ["exchange.get_ticker"],
                }
            },
        }
    )
    broker = ToolBrokerV1(
        runs_root=tmp_path / "runs",
        tool_spec=_spec(),
        connector_invoker=invoker,
        policy_engine=PolicyEngineV1(policy),
        approval_gateway=approval_gateway,
    )

    response = broker.dispatch(_request(), allowed_capabilities=["exchange.read"])
    assert response.status == "approval_required"
    assert response.error is not None
    assert response.error.code == "APPROVAL_REQUIRED"
    assert response.error.details["approval_id"].startswith("apr-")
    assert invoker.calls == 0


def test_tool_broker_executes_after_explicit_approval(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"price": 101.5}}])
    approval_gateway = ApprovalGatewayV1(tmp_path / "runs")
    policy = PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_approval_exec",
            "defaults": {"deny_by_default": True},
            "agents": {
                "agent_1": {
                    "role": "trader",
                    "allowed_capabilities": ["exchange.read"],
                    "approval_required_ops": ["exchange.get_ticker"],
                }
            },
        }
    )
    broker = ToolBrokerV1(
        runs_root=tmp_path / "runs",
        tool_spec=_spec(),
        connector_invoker=invoker,
        policy_engine=PolicyEngineV1(policy),
        approval_gateway=approval_gateway,
    )

    first = broker.dispatch(_request(), allowed_capabilities=["exchange.read"])
    assert first.status == "approval_required"
    assert first.error is not None
    approval_id_obj = first.error.details.get("approval_id")
    assert isinstance(approval_id_obj, str)
    approval_id = approval_id_obj
    approved = approval_gateway.approve(approval_id)
    assert approved.status is ApprovalStatus.APPROVED

    second = broker.dispatch(
        _request().model_copy(update={"approval_id": approval_id}),
        allowed_capabilities=["exchange.read"],
    )
    assert second.status == "ok"
    assert invoker.calls == 1

    events = load_run_events(tmp_path / "runs" / "run_1")
    assert RunEventType.APPROVAL_REQUESTED in {event.event_type for event in events}
