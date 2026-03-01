import pytest
from pydantic import ValidationError

from agentforge.contracts.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
)


def test_execution_request_valid_payload() -> None:
    request = ExecutionRequest(
        run_id="run-001",
        node_id="node-1",
        agent_id="agent.research",
        operation="pipeline",
        runtime="python",
        inputs=["request_json", "docs_ranked"],
        timeout_s=30,
        policy_snapshot={"terminal_access": "restricted"},
    )

    assert request.runtime.value == "python"
    assert request.inputs == ["request_json", "docs_ranked"]


def test_execution_request_rejects_invalid_fields() -> None:
    with pytest.raises(ValidationError, match="must be non-empty"):
        ExecutionRequest(
            run_id=" ",
            node_id="node-1",
            agent_id="agent.research",
            operation="pipeline",
            runtime="python",
            timeout_s=30,
        )

    with pytest.raises(ValidationError, match="timeout_s must be > 0"):
        ExecutionRequest(
            run_id="run-001",
            node_id="node-1",
            agent_id="agent.research",
            operation="pipeline",
            runtime="python",
            timeout_s=0,
        )


def test_execution_result_valid_payload() -> None:
    result = ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        produced_artifacts=[
            {
                "name": "digest_json",
                "type": "json",
                "path": "steps/01_node/outputs/digest.json",
                "sha256": "abc",
                "producer_step_id": "node-1",
            }
        ],
        metrics={"count": 2},
        latency_ms=42,
        adapter="python-runtime",
        adapter_version="1.0.0",
    )

    assert result.status is ExecutionStatus.SUCCESS
    assert result.produced_artifacts[0].name == "digest_json"


def test_execution_result_rejects_invalid_payload() -> None:
    with pytest.raises(ValidationError, match="string fields must be non-empty"):
        ExecutionResult(
            status="failed",
            produced_artifacts=[],
            metrics={},
            error="",
            adapter="python-runtime",
        )

    with pytest.raises(ValidationError, match="latency_ms must be >= 0"):
        ExecutionResult(
            status="failed",
            produced_artifacts=[],
            metrics={},
            adapter="python-runtime",
            latency_ms=-1,
        )
