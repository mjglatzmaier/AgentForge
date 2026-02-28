from __future__ import annotations

import sys
from pathlib import Path

from agentforge.control.adapters import (
    CommandRuntimeAdapter,
    ContainerRuntimeAdapter,
    PythonRuntimeAdapter,
)
from agentforge.contracts.models import ExecutionRequest, ExecutionStatus


def _request(*, metadata: dict[str, object], runtime: str) -> ExecutionRequest:
    return ExecutionRequest(
        run_id="run-001",
        node_id="node-1",
        agent_id="agent.test",
        operation="pipeline",
        runtime=runtime,
        inputs=["request_json"],
        timeout_s=10,
        metadata=metadata,
    )


def _python_entrypoint_ok(request: ExecutionRequest) -> dict[str, object]:
    return {"status": "success", "metrics": {"count": len(request.inputs)}}


def test_python_runtime_adapter_executes_module_function_entrypoint() -> None:
    adapter = PythonRuntimeAdapter()
    request = _request(
        runtime="python",
        metadata={"entrypoint": "agentforge.tests.control.test_adapters:_python_entrypoint_ok"},
    )

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.metrics["count"] == 1
    assert result.adapter == "python-runtime"


def test_python_runtime_adapter_returns_failed_on_bad_entrypoint() -> None:
    adapter = PythonRuntimeAdapter()
    request = _request(runtime="python", metadata={"entrypoint": "bad.entrypoint"})

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None


def test_command_runtime_adapter_executes_command_template() -> None:
    adapter = CommandRuntimeAdapter()
    request = _request(
        runtime="command",
        metadata={
            "command": [sys.executable, "-c", "print('ok')"],
            "cwd": str(Path.cwd()),
        },
    )

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.metrics["returncode"] == 0
    assert result.adapter == "command-runtime"


def test_command_runtime_adapter_returns_failed_on_nonzero_exit() -> None:
    adapter = CommandRuntimeAdapter()
    request = _request(
        runtime="command",
        metadata={"command": [sys.executable, "-c", "import sys; sys.exit(3)"]},
    )

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.metrics["returncode"] == 3


def test_container_runtime_adapter_is_stub() -> None:
    adapter = ContainerRuntimeAdapter()
    request = _request(runtime="container", metadata={})

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error == "Container runtime adapter is not implemented."
