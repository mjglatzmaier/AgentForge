from __future__ import annotations

import pytest

from agentforge.control.plugin_contract import dispatch_plugin_operation
from agentforge.contracts.models import ExecutionRequest, ExecutionResult, ExecutionStatus


def _request(
    *,
    operation: str = "fetch_and_snapshot",
    inputs: list[str] | None = None,
    input_artifacts: dict[str, object] | None = None,
) -> ExecutionRequest:
    return ExecutionRequest(
        run_id="run-001",
        node_id="node-1",
        agent_id="agent.test",
        operation=operation,
        runtime="python",
        inputs=list(inputs or []),
        timeout_s=30,
        metadata={"input_artifacts": dict(input_artifacts or {})},
    )


def _artifact_payload(name: str) -> dict[str, str]:
    return {
        "name": name,
        "type": "json",
        "path": f"steps/00_node/outputs/{name}.json",
        "sha256": "a" * 64,
        "producer_step_id": "node-0",
    }


def _success(_request: ExecutionRequest) -> ExecutionResult:
    return ExecutionResult(status=ExecutionStatus.SUCCESS, adapter="plugin-test")


def test_dispatch_plugin_operation_routes_by_request_operation() -> None:
    called: list[str] = []

    def fetch_handler(request: ExecutionRequest) -> ExecutionResult:
        called.append(f"fetch:{request.operation}")
        return ExecutionResult(status=ExecutionStatus.SUCCESS, adapter="plugin-test")

    def render_handler(_request: ExecutionRequest) -> ExecutionResult:
        called.append("render")
        return ExecutionResult(status=ExecutionStatus.SUCCESS, adapter="plugin-test")

    request = _request(
        operation="fetch_and_snapshot",
        inputs=["papers_raw"],
        input_artifacts={"papers_raw": _artifact_payload("papers_raw")},
    )
    result = dispatch_plugin_operation(
        request,
        operations={
            "fetch_and_snapshot": fetch_handler,
            "render_report": render_handler,
        },
    )

    assert result.status is ExecutionStatus.SUCCESS
    assert called == ["fetch:fetch_and_snapshot"]


def test_dispatch_plugin_operation_rejects_unknown_operation() -> None:
    request = _request(operation="unknown_op")
    with pytest.raises(ValueError, match="Unsupported plugin operation"):
        dispatch_plugin_operation(request, operations={"fetch_and_snapshot": _success})


def test_dispatch_plugin_operation_requires_manifest_indexed_inputs() -> None:
    request = _request(
        inputs=["papers_raw"],
        input_artifacts={},
    )
    with pytest.raises(ValueError, match="missing from metadata.input_artifacts"):
        dispatch_plugin_operation(request, operations={"fetch_and_snapshot": _success})


def test_dispatch_plugin_operation_rejects_input_name_mismatch() -> None:
    request = _request(
        inputs=["papers_raw"],
        input_artifacts={"papers_raw": _artifact_payload("not_papers_raw")},
    )
    with pytest.raises(ValueError, match="must use manifest artifact names"):
        dispatch_plugin_operation(request, operations={"fetch_and_snapshot": _success})


def test_dispatch_plugin_operation_requires_execution_result_return_type() -> None:
    request = _request(
        inputs=["papers_raw"],
        input_artifacts={"papers_raw": _artifact_payload("papers_raw")},
    )

    def wrong_type(_request: ExecutionRequest) -> dict[str, str]:
        return {"status": "success"}

    with pytest.raises(TypeError, match="must return ExecutionResult"):
        dispatch_plugin_operation(request, operations={"fetch_and_snapshot": wrong_type})
