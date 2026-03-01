from __future__ import annotations

import sys
from pathlib import Path

from agentforge.control.adapters import (
    CommandRuntimeAdapter,
    ContainerRuntimeAdapter,
    PythonRuntimeAdapter,
)
from agentforge.contracts.models import ExecutionRequest, ExecutionStatus


def _request(
    *, metadata: dict[str, object], runtime: str, policy_snapshot: dict[str, object] | None = None
) -> ExecutionRequest:
    return ExecutionRequest(
        run_id="run-001",
        node_id="node-1",
        agent_id="agent.test",
        operation="pipeline",
        runtime=runtime,
        inputs=["request_json"],
        timeout_s=10,
        policy_snapshot=dict(policy_snapshot or {}),
        metadata=metadata,
    )


def _python_entrypoint_ok(request: ExecutionRequest) -> dict[str, object]:
    return {"status": "success", "metrics": {"count": len(request.inputs)}}


def _python_entrypoint_windows_artifact(_request: ExecutionRequest) -> dict[str, object]:
    return {
        "status": "success",
        "produced_artifacts": [
            {
                "name": "result_json",
                "type": "json",
                "path": "steps\\01_node\\outputs\\result.json",
                "sha256": "a" * 64,
                "producer_step_id": "01_node",
            }
        ],
    }


def _python_entrypoint_bad_artifact(_request: ExecutionRequest) -> dict[str, object]:
    return {
        "status": "success",
        "produced_artifacts": [
            {
                "name": "result_json",
                "type": "json",
                "path": "../result.json",
                "sha256": "a" * 64,
                "producer_step_id": "01_node",
            }
        ],
    }


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


def test_command_runtime_adapter_enforces_allowed_commands() -> None:
    adapter = CommandRuntimeAdapter()
    request = _request(
        runtime="command",
        metadata={
            "command": ["python-not-allowed", "-c", "print('x')"],
            "cwd": str(Path.cwd()),
        },
        policy_snapshot={
            "terminal_access": "restricted",
            "allowed_commands": [sys.executable],
            "fs_scope": [str(Path.cwd())],
            "network_access": "none",
            "network_allowlist": [],
        },
    )

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert "not allowed" in result.error


def test_command_runtime_adapter_enforces_fs_scope() -> None:
    adapter = CommandRuntimeAdapter()
    request = _request(
        runtime="command",
        metadata={
            "command": [sys.executable, "-c", "print('x')"],
            "cwd": str(Path.cwd()),
        },
        policy_snapshot={
            "terminal_access": "restricted",
            "allowed_commands": [sys.executable],
            "fs_scope": [str(Path.cwd().parent / "outside_scope_dir")],
            "network_access": "none",
            "network_allowlist": [],
        },
    )

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert "outside operations_policy.fs_scope" in result.error


def test_python_runtime_adapter_enforces_network_allowlist() -> None:
    adapter = PythonRuntimeAdapter()
    request = _request(
        runtime="python",
        metadata={
            "entrypoint": "agentforge.tests.control.test_adapters:_python_entrypoint_ok",
            "cwd": str(Path.cwd()),
            "network_targets": ["blocked.example"],
        },
        policy_snapshot={
            "terminal_access": "none",
            "allowed_commands": [],
            "fs_scope": [str(Path.cwd())],
            "network_access": "allowlist",
            "network_allowlist": ["allowed.example"],
        },
    )

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert "not allowed" in result.error


def test_python_runtime_adapter_normalizes_artifact_paths_to_posix() -> None:
    adapter = PythonRuntimeAdapter()
    request = _request(
        runtime="python",
        metadata={
            "entrypoint": "agentforge.tests.control.test_adapters:_python_entrypoint_windows_artifact"
        },
    )

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.produced_artifacts[0].path == "steps/01_node/outputs/result.json"


def test_python_runtime_adapter_rejects_unsafe_artifact_path() -> None:
    adapter = PythonRuntimeAdapter()
    request = _request(
        runtime="python",
        metadata={"entrypoint": "agentforge.tests.control.test_adapters:_python_entrypoint_bad_artifact"},
    )

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert "must not contain '..'" in result.error


def test_command_runtime_adapter_rejects_unsupported_os(monkeypatch) -> None:
    monkeypatch.setattr("agentforge.control.adapters.platform.system", lambda: "Windows")
    adapter = CommandRuntimeAdapter()
    request = _request(
        runtime="command",
        metadata={"command": [sys.executable, "-c", "print('ok')"]},
    )

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert "only Unix/macOS are supported" in result.error


def test_container_runtime_adapter_is_stub() -> None:
    adapter = ContainerRuntimeAdapter()
    request = _request(runtime="container", metadata={})

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error == "Unsupported runtime for V1: container runtime adapter is not implemented."


def test_command_runtime_adapter_supports_json_stdio_contract() -> None:
    adapter = CommandRuntimeAdapter()
    script = (
        "import json,sys;"
        "json.load(sys.stdin);"
        "print(json.dumps({'schema_version':1,'result':{"
        "'status':'success',"
        "'produced_artifacts':[{'name':'result_json','type':'json','path':'steps\\\\01_node\\\\outputs\\\\result.json','sha256':'"
        + ("a" * 64)
        + "','producer_step_id':'node-1'}],"
        "'metrics':{'interop':'ok'},"
        "'adapter':'plugin-js'"
        "}}))"
    )
    request = _request(
        runtime="command",
        metadata={
            "command": [sys.executable, "-c", script],
            "cwd": str(Path.cwd()),
            "io_contract": "json-stdio",
        },
    )

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.metrics["interop"] == "ok"
    assert result.produced_artifacts[0].path == "steps/01_node/outputs/result.json"
    assert result.adapter == "command-runtime"


def test_command_runtime_adapter_rejects_invalid_json_stdio_payload() -> None:
    adapter = CommandRuntimeAdapter()
    script = "import sys; sys.stdin.read(); print('not-json')"
    request = _request(
        runtime="command",
        metadata={
            "command": [sys.executable, "-c", script],
            "cwd": str(Path.cwd()),
            "io_contract": "json-stdio",
        },
    )

    result = adapter.execute(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert "invalid JSON" in result.error
