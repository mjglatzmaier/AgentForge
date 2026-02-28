"""Execution runtime adapters for control-plane nodes."""

from __future__ import annotations

from abc import ABC, abstractmethod
from importlib import import_module
from time import perf_counter
from typing import Any, Callable
import subprocess

from agentforge.contracts.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionStatus,
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
            entrypoint = _required_metadata_string(request, "entrypoint")
            target = _resolve_entrypoint(entrypoint)
            payload = target(request)
            result = _coerce_execution_result(payload, adapter=self.name, version=self.version)
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
            command = _required_command(request)
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
