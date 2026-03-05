from __future__ import annotations

from pathlib import Path

from agentforge.sidecar.core.contracts.tool_contract_v1 import (
    ToolCallRequestV1,
    ToolCallResponseV1,
)
from agentforge.sidecar.core.policy.decision import PolicyDecisionResult


def test_sidecar_scaffold_packages_exist() -> None:
    root = Path(__file__).resolve().parents[2] / "sidecar"
    expected_init_paths = [
        "__init__.py",
        "agentd/__init__.py",
        "agentd/api/__init__.py",
        "agentd/approvals/__init__.py",
        "agentd/broker/__init__.py",
        "agentd/connectors/__init__.py",
        "agentd/kernel/__init__.py",
        "agentctl/__init__.py",
        "compat/__init__.py",
        "core/__init__.py",
        "core/contracts/__init__.py",
        "core/policy/__init__.py",
        "services/__init__.py",
        "services/arxiv/__init__.py",
        "services/exchanged/__init__.py",
        "services/gmaild/__init__.py",
        "services/rssd/__init__.py",
        "workbench/__init__.py",
    ]
    assert all((root / rel_path).is_file() for rel_path in expected_init_paths)


def test_sidecar_contract_models_construct() -> None:
    request = ToolCallRequestV1(
        request_id="req_1",
        run_id="run_1",
        node_id="node_1",
        agent_id="agent_1",
        capability="exchange.read",
        operation="exchange.get_ticker",
        trace={"correlation_id": "corr_1"},
    )
    response = ToolCallResponseV1(
        request_id=request.request_id,
        status="ok",
    )
    decision = PolicyDecisionResult(
        decision="allow",
        reason_code="CAPABILITY_ALLOWED",
        policy_snapshot_id="pol_1",
    )
    assert response.request_id == request.request_id
    assert decision.decision == "allow"

