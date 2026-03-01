"""Execution runtime adapters for control-plane nodes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import import_module
from time import perf_counter
from typing import Any, Callable
import subprocess
import platform
from pathlib import Path, PurePosixPath

from agentforge.contracts.models import (
    ArtifactRef,
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
    NetworkAccess,
    OperationsPolicy,
    TerminalAccess,
)


class RuntimeAdapter(ABC):
    """Base contract for runtime adapters."""

    name: str = "runtime"
    version: str = "1"

    @abstractmethod
    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute one request and return a typed result envelope."""


class PythonRuntimeAdapter(RuntimeAdapter):
    """Execute a Python module:function entrypoint."""

    name = "python-runtime"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        started = perf_counter()
        try:
            _enforce_v1_os_support()
            _enforce_policy(request, command=None)
            entrypoint = _required_metadata_string(request, "entrypoint")
            target = _resolve_entrypoint(entrypoint)
            payload = target(request)
            result = _coerce_execution_result(payload, adapter=self.name, version=self.version)
            result = _normalize_result_artifact_paths(result)
            if result.latency_ms is None:
                result.latency_ms = int((perf_counter() - started) * 1000)
            return result
        except Exception as exc:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error=str(exc),
                traceback_excerpt=type(exc).__name__,
                latency_ms=int((perf_counter() - started) * 1000),
                adapter=self.name,
                adapter_version=self.version,
            )


class CommandRuntimeAdapter(RuntimeAdapter):
    """Execute a command-template entrypoint (supports npm/node tooling)."""

    name = "command-runtime"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        started = perf_counter()
        try:
            _enforce_v1_os_support()
            command = _required_command(request)
            _enforce_policy(request, command=command)
            cwd = request.metadata.get("cwd")
            cwd_path = str(cwd).strip() if isinstance(cwd, str) and cwd.strip() else None
            completed = subprocess.run(
                command,
                cwd=cwd_path,
                capture_output=True,
                text=True,
                timeout=request.timeout_s,
                check=False,
            )
            status = (
                ExecutionStatus.SUCCESS if completed.returncode == 0 else ExecutionStatus.FAILED
            )
            error_excerpt = None
            if status is ExecutionStatus.FAILED:
                error_excerpt = (completed.stderr or completed.stdout).strip()[:500] or (
                    f"Command exited with returncode={completed.returncode}"
                )
            return ExecutionResult(
                status=status,
                metrics={"returncode": completed.returncode},
                error=error_excerpt,
                latency_ms=int((perf_counter() - started) * 1000),
                adapter=self.name,
                adapter_version=self.version,
            )
        except Exception as exc:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error=str(exc),
                traceback_excerpt=type(exc).__name__,
                latency_ms=int((perf_counter() - started) * 1000),
                adapter=self.name,
                adapter_version=self.version,
            )


class ContainerRuntimeAdapter(RuntimeAdapter):
    """Stub adapter for future containerized execution."""

    name = "container-runtime"

    def execute(self, request: ExecutionRequest) -> ExecutionResult:
        try:
            _enforce_v1_os_support()
        except Exception as exc:
            return ExecutionResult(
                status=ExecutionStatus.FAILED,
                error=str(exc),
                traceback_excerpt=type(exc).__name__,
                adapter=self.name,
                adapter_version=self.version,
                latency_ms=0,
            )
        return ExecutionResult(
            status=ExecutionStatus.FAILED,
            error="Container runtime adapter is not implemented.",
            adapter=self.name,
            adapter_version=self.version,
            latency_ms=0,
        )


def _required_metadata_string(request: ExecutionRequest, key: str) -> str:
    value = request.metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"ExecutionRequest metadata.{key} must be a non-empty string.")
    return value.strip()


def _required_command(request: ExecutionRequest) -> list[str]:
    command = request.metadata.get("command")
    if isinstance(command, str) and command.strip():
        return [command.strip()]
    if isinstance(command, list) and command:
        normalized: list[str] = []
        for item in command:
            if not isinstance(item, str) or not item.strip():
                raise ValueError("ExecutionRequest metadata.command list entries must be non-empty strings.")
            normalized.append(item.strip())
        return normalized
    raise ValueError("ExecutionRequest metadata.command must be a non-empty string or string list.")


def _resolve_entrypoint(ref: str) -> Callable[[ExecutionRequest], Any]:
    if ref.count(":") != 1:
        raise ValueError(f"Invalid entrypoint '{ref}': expected format 'module.path:function'")
    module_name, func_name = ref.split(":", maxsplit=1)
    if not module_name or not func_name:
        raise ValueError(f"Invalid entrypoint '{ref}': expected format 'module.path:function'")
    try:
        module = import_module(module_name)
    except ModuleNotFoundError as exc:
        raise ValueError(f"Entrypoint module not found for '{ref}': {module_name}") from exc
    if not hasattr(module, func_name):
        raise ValueError(f"Entrypoint function not found for '{ref}': {func_name}")
    target = getattr(module, func_name)
    if not callable(target):
        raise TypeError(f"Entrypoint is not callable for '{ref}': {func_name}")
    return target


def _coerce_execution_result(payload: Any, *, adapter: str, version: str) -> ExecutionResult:
    if isinstance(payload, ExecutionResult):
        return payload
    if not isinstance(payload, dict):
        raise TypeError(
            "Python runtime entrypoint must return ExecutionResult or dict-compatible payload."
        )
    payload_with_defaults = dict(payload)
    payload_with_defaults.setdefault("status", ExecutionStatus.SUCCESS)
    payload_with_defaults.setdefault("adapter", adapter)
    payload_with_defaults.setdefault("adapter_version", version)
    return ExecutionResult.model_validate(payload_with_defaults)


def _enforce_policy(request: ExecutionRequest, *, command: list[str] | None) -> None:
    if not request.policy_snapshot:
        return

    policy = OperationsPolicy.model_validate(request.policy_snapshot)
    _enforce_terminal_policy(policy, command=command)
    _enforce_fs_scope(policy, request=request)
    _enforce_network_policy(policy, request=request)


def _enforce_terminal_policy(policy: OperationsPolicy, *, command: list[str] | None) -> None:
    if command is None:
        return

    if policy.terminal_access is TerminalAccess.NONE:
        raise ValueError("Terminal execution is disallowed by operations_policy.")

    if policy.allowed_commands:
        executable = command[0]
        if executable not in policy.allowed_commands:
            raise ValueError(
                f"Command '{executable}' is not allowed by operations_policy.allowed_commands."
            )


def _enforce_fs_scope(policy: OperationsPolicy, *, request: ExecutionRequest) -> None:
    if not policy.fs_scope:
        return

    cwd = request.metadata.get("cwd")
    if not isinstance(cwd, str) or not cwd.strip():
        raise ValueError("ExecutionRequest metadata.cwd is required when operations_policy.fs_scope is set.")
    cwd_path = Path(cwd).resolve()

    allowed = False
    for scope in policy.fs_scope:
        scope_path = Path(scope)
        if not scope_path.is_absolute():
            scope_path = (Path.cwd() / scope_path).resolve()
        else:
            scope_path = scope_path.resolve()
        if _is_within(cwd_path, scope_path):
            allowed = True
            break
    if not allowed:
        raise ValueError(f"cwd '{cwd_path}' is outside operations_policy.fs_scope.")


def _enforce_network_policy(policy: OperationsPolicy, *, request: ExecutionRequest) -> None:
    targets_raw = request.metadata.get("network_targets")
    if targets_raw is None:
        return
    if not isinstance(targets_raw, list):
        raise ValueError("ExecutionRequest metadata.network_targets must be a list of host strings.")

    targets: list[str] = []
    for item in targets_raw:
        if not isinstance(item, str) or not item.strip():
            raise ValueError("ExecutionRequest metadata.network_targets entries must be non-empty strings.")
        targets.append(item.strip())

    if not targets:
        return

    if policy.network_access is NetworkAccess.NONE:
        raise ValueError("Network access is disallowed by operations_policy.")

    allowlist = set(policy.network_allowlist)
    disallowed = [target for target in targets if target not in allowlist]
    if disallowed:
        raise ValueError(
            "Network target(s) not allowed by operations_policy.network_allowlist: "
            + ", ".join(disallowed)
        )


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _enforce_v1_os_support() -> None:
    if platform.system() not in {"Darwin", "Linux"}:
        raise ValueError("Unsupported OS for V1 runtime adapters: only Unix/macOS are supported.")


def _normalize_result_artifact_paths(result: ExecutionResult) -> ExecutionResult:
    if not result.produced_artifacts:
        return result

    normalized: list[ArtifactRef] = []
    for artifact in result.produced_artifacts:
        normalized_path = _normalize_posix_artifact_path(artifact.path)
        normalized.append(artifact.model_copy(update={"path": normalized_path}))
    return result.model_copy(update={"produced_artifacts": normalized})


def _normalize_posix_artifact_path(path: str) -> str:
    replaced = path.replace("\\", "/").strip()
    if not replaced:
        raise ValueError("Artifact path must be non-empty.")
    if replaced.startswith("/") or (len(replaced) >= 2 and replaced[1] == ":"):
        raise ValueError("Artifact path must be relative and POSIX-style.")
    posix = PurePosixPath(replaced)
    if ".." in posix.parts:
        raise ValueError("Artifact path must not contain '..'.")
    return posix.as_posix()
