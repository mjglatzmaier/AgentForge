"""Typed plugin execution contract helpers."""

from __future__ import annotations

from typing import Mapping, Protocol

from agentforge.contracts.models import ArtifactRef, ExecutionRequest, ExecutionResult


class PluginEntrypoint(Protocol):
    """Canonical plugin entrypoint type."""

    def __call__(self, request: ExecutionRequest) -> ExecutionResult: ...


def dispatch_plugin_operation(
    request: ExecutionRequest,
    *,
    operations: Mapping[str, PluginEntrypoint],
) -> ExecutionResult:
    """Dispatch one plugin operation strictly by request.operation."""

    operation = request.operation.strip()
    handler = operations.get(operation)
    if handler is None:
        raise ValueError(f"Unsupported plugin operation '{operation}'.")
    _require_manifest_indexed_inputs(request)
    result = handler(request)
    if not isinstance(result, ExecutionResult):
        raise TypeError("Plugin operation handlers must return ExecutionResult.")
    return result


def _require_manifest_indexed_inputs(request: ExecutionRequest) -> dict[str, ArtifactRef]:
    raw_inputs = request.metadata.get("input_artifacts")
    if not request.inputs:
        if raw_inputs is None:
            return {}
        if not isinstance(raw_inputs, dict):
            raise ValueError("ExecutionRequest metadata.input_artifacts must be a mapping.")
        return {}

    if not isinstance(raw_inputs, dict):
        raise ValueError("ExecutionRequest metadata.input_artifacts is required for plugin inputs.")

    resolved: dict[str, ArtifactRef] = {}
    for input_name in request.inputs:
        if input_name not in raw_inputs:
            raise ValueError(
                f"ExecutionRequest input '{input_name}' missing from metadata.input_artifacts."
            )
        artifact = ArtifactRef.model_validate(raw_inputs[input_name])
        if artifact.name != input_name:
            raise ValueError(
                "ExecutionRequest metadata.input_artifacts entries must use manifest artifact names."
            )
        resolved[input_name] = artifact
    return resolved
