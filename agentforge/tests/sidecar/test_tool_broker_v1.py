from __future__ import annotations

from pathlib import Path
from typing import Any

from agentforge.sidecar.agentd.approvals.store_v1 import ApprovalGatewayV1
from agentforge.sidecar.agentd.broker.audit_store_v1 import load_audit_events
from agentforge.sidecar.agentd.broker.error_mapper_v1 import map_connector_exception
from agentforge.sidecar.agentd.broker.events_store import load_run_events
from agentforge.sidecar.agentd.broker.tool_broker_v1 import ToolBrokerV1
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


def _single_operation_spec(
    *,
    op_id: str,
    required_capability: str,
    input_schema: dict[str, str],
    output_schema: dict[str, str],
) -> ToolSpecV1:
    return ToolSpecV1(
        name=f"{op_id}-tool",
        version="1.0.0",
        operations=[
            ToolOperationSpecV1(
                op_id=op_id,
                required_capabilities=[required_capability],
                input_schema=input_schema,
                output_schema=output_schema,
                timeout_s=1.0,
                max_retries=0,
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
    assert approved.approval_token_id is not None

    second = broker.dispatch(
        _request().model_copy(update={"approval_token": approved.approval_token_id}),
        allowed_capabilities=["exchange.read"],
    )
    assert second.status == "ok"
    assert invoker.calls == 1

    events = load_run_events(tmp_path / "runs" / "run_1")
    assert RunEventType.APPROVAL_REQUESTED in {event.event_type for event in events}


def test_tool_broker_rejects_reused_approval_token(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"price": 101.5}}, {"output": {"price": 101.5}}])
    approval_gateway = ApprovalGatewayV1(tmp_path / "runs")
    policy = PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_approval_reuse",
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
    approved = approval_gateway.approve(approval_id_obj)
    assert approved.approval_token_id is not None

    ok_response = broker.dispatch(
        _request().model_copy(update={"approval_token": approved.approval_token_id}),
        allowed_capabilities=["exchange.read"],
    )
    assert ok_response.status == "ok"

    reused_response = broker.dispatch(
        _request().model_copy(update={"approval_token": approved.approval_token_id}),
        allowed_capabilities=["exchange.read"],
    )
    assert reused_response.status == "denied"
    assert reused_response.error is not None
    assert reused_response.error.code == "APPROVAL_TOKEN_USED"


def test_tool_broker_denies_when_domain_constraint_fails(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"body": "ok"}}])
    request = ToolCallRequestV1(
        request_id="req_domain_1",
        run_id="run_domain_1",
        node_id="node_domain_1",
        agent_id="agent_1",
        capability="net.read",
        operation="net.fetch",
        input={"url": "https://evil.example/path"},
        trace={"correlation_id": "corr_domain_1"},
    )
    policy = PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_domain",
            "defaults": {"deny_by_default": True},
            "agents": {
                "agent_1": {
                    "role": "reader",
                    "allowed_capabilities": ["net.read"],
                    "constraints": {"net.fetch": {"domain_allowlist": ["example.com"]}},
                }
            },
        }
    )
    broker = ToolBrokerV1(
        runs_root=tmp_path / "runs",
        tool_spec=_single_operation_spec(
            op_id="net.fetch",
            required_capability="net.read",
            input_schema={"url": "str"},
            output_schema={"body": "str"},
        ),
        connector_invoker=invoker,
        policy_engine=PolicyEngineV1(policy),
    )

    response = broker.dispatch(request, allowed_capabilities=["net.read"])
    assert response.status == "denied"
    assert response.error is not None
    assert response.error.code == "CONSTRAINT_DOMAIN_NOT_ALLOWED"
    assert invoker.calls == 0


def test_tool_broker_denies_when_recipient_constraint_fails(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"message_id": "msg_1"}}])
    request = ToolCallRequestV1(
        request_id="req_recipient_1",
        run_id="run_recipient_1",
        node_id="node_recipient_1",
        agent_id="agent_1",
        capability="email.send",
        operation="gmail.send",
        input={"to": "blocked@example.com"},
        trace={"correlation_id": "corr_recipient_1"},
    )
    policy = PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_recipient",
            "defaults": {"deny_by_default": True},
            "agents": {
                "agent_1": {
                    "role": "mailer",
                    "allowed_capabilities": ["email.send"],
                    "constraints": {
                        "gmail.send": {"recipient_allowlist": ["allowed@example.com"]}
                    },
                }
            },
        }
    )
    broker = ToolBrokerV1(
        runs_root=tmp_path / "runs",
        tool_spec=_single_operation_spec(
            op_id="gmail.send",
            required_capability="email.send",
            input_schema={"to": "str"},
            output_schema={"message_id": "str"},
        ),
        connector_invoker=invoker,
        policy_engine=PolicyEngineV1(policy),
    )

    response = broker.dispatch(request, allowed_capabilities=["email.send"])
    assert response.status == "denied"
    assert response.error is not None
    assert response.error.code == "CONSTRAINT_RECIPIENT_NOT_ALLOWED"
    assert invoker.calls == 0


def test_tool_broker_denies_when_symbol_or_notional_constraint_fails(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"order_id": "ord_1"}}])
    policy = PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_trade_constraints",
            "defaults": {"deny_by_default": True},
            "agents": {
                "agent_1": {
                    "role": "trader",
                    "allowed_capabilities": ["exchange.trade"],
                    "constraints": {
                        "exchange.place_order": {
                            "symbol_allowlist": ["btc-usd"],
                            "max_notional_usd": 1000.0,
                        }
                    },
                }
            },
        }
    )
    broker = ToolBrokerV1(
        runs_root=tmp_path / "runs",
        tool_spec=_single_operation_spec(
            op_id="exchange.place_order",
            required_capability="exchange.trade",
            input_schema={"symbol": "str", "notional_usd": "float"},
            output_schema={"order_id": "str"},
        ),
        connector_invoker=invoker,
        policy_engine=PolicyEngineV1(policy),
    )

    symbol_denied = broker.dispatch(
        ToolCallRequestV1(
            request_id="req_trade_symbol_1",
            run_id="run_trade_1",
            node_id="node_trade_1",
            agent_id="agent_1",
            capability="exchange.trade",
            operation="exchange.place_order",
            input={"symbol": "eth-usd", "notional_usd": 500.0},
            trace={"correlation_id": "corr_trade_symbol_1"},
        ),
        allowed_capabilities=["exchange.trade"],
    )
    assert symbol_denied.status == "denied"
    assert symbol_denied.error is not None
    assert symbol_denied.error.code == "CONSTRAINT_SYMBOL_NOT_ALLOWED"

    notional_denied = broker.dispatch(
        ToolCallRequestV1(
            request_id="req_trade_notional_1",
            run_id="run_trade_2",
            node_id="node_trade_2",
            agent_id="agent_1",
            capability="exchange.trade",
            operation="exchange.place_order",
            input={"symbol": "btc-usd", "notional_usd": 5000.0},
            trace={"correlation_id": "corr_trade_notional_1"},
        ),
        allowed_capabilities=["exchange.trade"],
    )
    assert notional_denied.status == "denied"
    assert notional_denied.error is not None
    assert notional_denied.error.code == "CONSTRAINT_NOTIONAL_EXCEEDED"
    assert invoker.calls == 0


def test_tool_broker_enforces_rate_limit_then_allows_valid_path(tmp_path: Path) -> None:
    invoker = _FakeInvoker(
        [
            {"output": {"price": 101.0}},
            {"output": {"price": 102.0}},
            {"output": {"price": 103.0}},
        ]
    )
    policy = PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_rate_limit",
            "defaults": {"deny_by_default": True},
            "agents": {
                "agent_1": {
                    "role": "reader",
                    "allowed_capabilities": ["exchange.read"],
                    "rate_limits": {"exchange.get_ticker": 2},
                    "constraints": {
                        "exchange.get_ticker": {"symbol_allowlist": ["btc-usd", "eth-usd"]}
                    },
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

    first = broker.dispatch(
        _request().model_copy(update={"request_id": "req_rate_1", "input": {"symbol": "btc-usd"}}),
        allowed_capabilities=["exchange.read"],
    )
    second = broker.dispatch(
        _request().model_copy(update={"request_id": "req_rate_2", "input": {"symbol": "eth-usd"}}),
        allowed_capabilities=["exchange.read"],
    )
    third = broker.dispatch(
        _request().model_copy(update={"request_id": "req_rate_3", "input": {"symbol": "btc-usd"}}),
        allowed_capabilities=["exchange.read"],
    )

    assert first.status == "ok"
    assert second.status == "ok"
    assert third.status == "denied"
    assert third.error is not None
    assert third.error.code == "RATE_LIMIT_EXCEEDED"
    assert invoker.calls == 2


def test_tool_broker_writes_audit_for_allow_deny_and_approval(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"price": 101.5}}])
    approval_gateway = ApprovalGatewayV1(tmp_path / "runs")
    policy = PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_audit_flow",
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

    denied = broker.dispatch(
        _request().model_copy(update={"capability": "exchange.write", "request_id": "req_audit_deny"}),
        allowed_capabilities=["exchange.write"],
    )
    assert denied.status == "denied"

    approval_required = broker.dispatch(
        _request().model_copy(update={"request_id": "req_audit_exec"}),
        allowed_capabilities=["exchange.read"],
    )
    assert approval_required.status == "approval_required"
    assert approval_required.error is not None
    approval_id_obj = approval_required.error.details.get("approval_id")
    assert isinstance(approval_id_obj, str)
    approved = approval_gateway.approve(approval_id_obj)
    assert approved.approval_token_id is not None

    allowed = broker.dispatch(
        _request().model_copy(
            update={"request_id": "req_audit_exec", "approval_token": approved.approval_token_id}
        ),
        allowed_capabilities=["exchange.read"],
    )
    assert allowed.status == "ok"

    decisions = {event.decision for event in load_audit_events(tmp_path / "runs")}
    assert "deny" in decisions
    assert "require_approval" in decisions
    assert "allow" in decisions


def test_tool_broker_redacts_sensitive_fields_in_persisted_events(tmp_path: Path) -> None:
    invoker = _FakeInvoker([{"output": {"price": 101.5}}])
    broker = ToolBrokerV1(runs_root=tmp_path / "runs", tool_spec=_spec(), connector_invoker=invoker)
    request = _request().model_copy(
        update={
            "request_id": "req_redact_1",
            "input": {
                "symbol": "BTC-USD",
                "api_key": "plain-key",
                "headers": {"authorization": "Bearer secret-token"},
            },
        }
    )
    response = broker.dispatch(request, allowed_capabilities=["exchange.read"])
    assert response.status == "ok"

    events = load_run_events(tmp_path / "runs" / "run_1")
    request_event = next(event for event in events if event.event_type == RunEventType.TOOL_CALL_REQUESTED)
    assert request_event.payload["input"]["api_key"] == "[REDACTED]"
    assert request_event.payload["input"]["headers"]["authorization"] == "[REDACTED]"


def test_error_mapper_produces_bounded_error_codes() -> None:
    assert map_connector_exception(ValueError("bad input")).code == "INVALID_REQUEST"
    assert map_connector_exception(PermissionError("blocked")).code == "POLICY_DENIED"
    assert map_connector_exception(RuntimeError("upstream down")).code == "UPSTREAM_ERROR"
