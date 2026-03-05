"""Tool broker v1 for schema checks, capability gates, retries/timeouts, and event logging."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Mapping

from agentforge.sidecar.agentd.broker.events_store import append_run_event, create_run_event
from agentforge.sidecar.core.contracts.events_v1 import RunEventType
from agentforge.sidecar.core.contracts.tool_contract_v1 import (
    ToolCallErrorV1,
    ToolCallRequestV1,
    ToolCallResponseV1,
    ToolOperationSpecV1,
    ToolSpecV1,
)

_SCHEMA_TYPE_MAP: dict[str, type[Any]] = {
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "object": dict,
    "array": list,
}


class ToolBrokerV1:
    """Dispatch connector operations through ToolSpec policy and schema checks."""

    def __init__(
        self,
        *,
        runs_root: str | Path,
        tool_spec: ToolSpecV1,
        connector_invoker: Any,
    ) -> None:
        self._runs_root = Path(runs_root)
        self._tool_spec = tool_spec
        self._connector_invoker = connector_invoker

    def dispatch(
        self,
        request: ToolCallRequestV1,
        *,
        allowed_capabilities: list[str],
    ) -> ToolCallResponseV1:
        run_dir = self._runs_root / request.run_id
        self._append_lifecycle_event(run_dir, request, RunEventType.TOOL_CALL_REQUESTED)

        operation = self._tool_spec.operation_by_id(request.operation)
        if operation is None:
            response = ToolCallResponseV1(
                request_id=request.request_id,
                status="error",
                error=ToolCallErrorV1(
                    code="INVALID_REQUEST",
                    message=f"Unsupported operation '{request.operation}'.",
                    retryable=False,
                ),
            )
            self._append_lifecycle_event(run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response)
            return response

        capability_error = self._validate_capability(
            request=request,
            operation=operation,
            allowed_capabilities=allowed_capabilities,
        )
        if capability_error is not None:
            response = ToolCallResponseV1(
                request_id=request.request_id,
                status="denied",
                error=capability_error,
            )
            self._append_lifecycle_event(run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response)
            return response

        schema_error = self._validate_payload_schema(
            payload=request.input,
            schema=operation.input_schema,
            schema_name="input",
        )
        if schema_error is not None:
            response = ToolCallResponseV1(
                request_id=request.request_id,
                status="error",
                error=schema_error,
            )
            self._append_lifecycle_event(run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response)
            return response

        response = self._invoke_with_retry(request=request, operation=operation)
        self._append_lifecycle_event(run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response)
        return response

    def _invoke_with_retry(
        self,
        *,
        request: ToolCallRequestV1,
        operation: ToolOperationSpecV1,
    ) -> ToolCallResponseV1:
        timeout_error: ToolCallErrorV1 | None = None
        last_error: ToolCallErrorV1 | None = None
        attempts = operation.max_retries + 1
        for _attempt in range(attempts):
            try:
                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(
                        self._connector_invoker.invoke,
                        request.model_dump(mode="json"),
                    )
                    connector_result = future.result(timeout=operation.timeout_s)
            except FuturesTimeoutError:
                timeout_error = ToolCallErrorV1(
                    code="CONNECTOR_TIMEOUT",
                    message=f"Operation timed out after {operation.timeout_s:.3f}s.",
                    retryable=True,
                )
                continue
            except Exception as exc:  # noqa: BLE001
                last_error = ToolCallErrorV1(
                    code="UPSTREAM_ERROR",
                    message=str(exc),
                    retryable=True,
                )
                continue

            if not isinstance(connector_result, Mapping):
                return ToolCallResponseV1(
                    request_id=request.request_id,
                    status="error",
                    error=ToolCallErrorV1(
                        code="UPSTREAM_ERROR",
                        message="Connector result must be a mapping.",
                        retryable=False,
                    ),
                )

            raw_output = connector_result.get("output", {})
            if not isinstance(raw_output, dict):
                return ToolCallResponseV1(
                    request_id=request.request_id,
                    status="error",
                    error=ToolCallErrorV1(
                        code="UPSTREAM_ERROR",
                        message="Connector output must be a mapping.",
                        retryable=False,
                    ),
                )
            output_error = self._validate_payload_schema(
                payload=raw_output,
                schema=operation.output_schema,
                schema_name="output",
            )
            if output_error is not None:
                return ToolCallResponseV1(
                    request_id=request.request_id,
                    status="error",
                    error=output_error,
                )

            return ToolCallResponseV1(
                request_id=request.request_id,
                status="ok",
                output=dict(raw_output),
            )

        if timeout_error is not None:
            return ToolCallResponseV1(
                request_id=request.request_id,
                status="timeout",
                error=timeout_error,
            )
        return ToolCallResponseV1(
            request_id=request.request_id,
            status="error",
            error=last_error
            or ToolCallErrorV1(
                code="UPSTREAM_ERROR",
                message="Connector invocation failed.",
                retryable=False,
            ),
        )

    def _validate_capability(
        self,
        *,
        request: ToolCallRequestV1,
        operation: ToolOperationSpecV1,
        allowed_capabilities: list[str],
    ) -> ToolCallErrorV1 | None:
        allowed = {value.strip() for value in allowed_capabilities if value.strip()}
        if request.capability not in allowed:
            return ToolCallErrorV1(
                code="POLICY_DENIED",
                message=f"Capability '{request.capability}' is not allowed for this agent.",
                retryable=False,
            )

        required = set(operation.required_capabilities)
        if request.capability not in required:
            return ToolCallErrorV1(
                code="POLICY_DENIED",
                message=f"Operation '{operation.op_id}' requires one of {sorted(required)}.",
                retryable=False,
            )
        return None

    def _validate_payload_schema(
        self,
        *,
        payload: Mapping[str, Any],
        schema: Mapping[str, str],
        schema_name: str,
    ) -> ToolCallErrorV1 | None:
        for field_name, field_type in schema.items():
            if field_name not in payload:
                return ToolCallErrorV1(
                    code="INVALID_REQUEST",
                    message=f"Missing {schema_name} field '{field_name}'.",
                    retryable=False,
                )
            expected_type = _SCHEMA_TYPE_MAP.get(field_type)
            if expected_type is None:
                return ToolCallErrorV1(
                    code="INTERNAL_ERROR",
                    message=f"Unsupported {schema_name} schema type '{field_type}'.",
                    retryable=False,
                )
            value = payload[field_name]
            if field_type == "float":
                if not isinstance(value, (int, float)):
                    return ToolCallErrorV1(
                        code="INVALID_REQUEST",
                        message=(
                            f"Field '{field_name}' expected type '{field_type}' "
                            f"but got '{type(value).__name__}'."
                        ),
                        retryable=False,
                    )
                continue
            if field_type == "int" and isinstance(value, bool):
                return ToolCallErrorV1(
                    code="INVALID_REQUEST",
                    message=(
                        f"Field '{field_name}' expected type '{field_type}' "
                        f"but got '{type(value).__name__}'."
                    ),
                    retryable=False,
                )
            if not isinstance(value, expected_type):
                return ToolCallErrorV1(
                    code="INVALID_REQUEST",
                    message=(
                        f"Field '{field_name}' expected type '{field_type}' "
                        f"but got '{type(value).__name__}'."
                    ),
                    retryable=False,
                )
        return None

    def _append_lifecycle_event(
        self,
        run_dir: Path,
        request: ToolCallRequestV1,
        event_type: RunEventType,
        response: ToolCallResponseV1 | None = None,
    ) -> None:
        payload: dict[str, object] = {
            "request_id": request.request_id,
            "agent_id": request.agent_id,
            "operation": request.operation,
            "capability": request.capability,
            "correlation_id": request.trace.correlation_id,
        }
        if request.trace.causation_id is not None:
            payload["causation_id"] = request.trace.causation_id
        if response is not None:
            payload["status"] = response.status
            if response.error is not None:
                payload["error_code"] = response.error.code
                payload["error_message"] = response.error.message
        event = create_run_event(
            run_id=request.run_id,
            event_type=event_type,
            step_id=request.node_id,
            payload=payload,
        )
        append_run_event(run_dir, event)
