"""Tool broker v1 for schema checks, capability gates, retries/timeouts, and event logging."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from pathlib import Path
from typing import Any, Mapping

from agentforge.sidecar.agentd.broker.audit_store_v1 import append_audit_event, create_audit_event
from agentforge.sidecar.agentd.broker.error_mapper_v1 import map_connector_exception
from agentforge.sidecar.agentd.broker.events_store import append_run_event, create_run_event
from agentforge.sidecar.core.contracts.approval_v1 import ApprovalStatus
from agentforge.sidecar.core.contracts.events_v1 import RunEventType
from agentforge.sidecar.core.contracts.tool_contract_v1 import (
    ToolCallErrorV1,
    ToolCallRequestV1,
    ToolCallResponseV1,
    ToolOperationSpecV1,
    ToolSpecV1,
)
from agentforge.sidecar.core.policy.engine_v1 import PolicyEngineV1
from agentforge.sidecar.core.redaction_v1 import redact_sensitive_data

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
        policy_engine: PolicyEngineV1 | None = None,
        approval_gateway: Any | None = None,
    ) -> None:
        self._runs_root = Path(runs_root)
        self._tool_spec = tool_spec
        self._connector_invoker = connector_invoker
        self._policy_engine = policy_engine
        self._approval_gateway = approval_gateway

    def dispatch(
        self,
        request: ToolCallRequestV1,
        *,
        allowed_capabilities: list[str] | None = None,
    ) -> ToolCallResponseV1:
        run_dir = self._runs_root / request.run_id
        self._append_lifecycle_event(run_dir, request, RunEventType.TOOL_CALL_REQUESTED)

        if self._policy_engine is not None:
            policy_decision = self._policy_engine.evaluate(
                agent_id=request.agent_id,
                capability=request.capability,
                operation=request.operation,
            )
            if policy_decision.decision == "deny":
                self._append_audit_event(
                    request=request,
                    decision="deny",
                    reason_code=policy_decision.reason_code,
                )
                response = ToolCallResponseV1(
                    request_id=request.request_id,
                    status="denied",
                    error=ToolCallErrorV1(
                        code="POLICY_DENIED",
                        message=f"Denied by policy ({policy_decision.reason_code}).",
                        retryable=False,
                        details={"policy_snapshot_id": policy_decision.policy_snapshot_id},
                    ),
                )
                self._append_lifecycle_event(run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response)
                return response
            if policy_decision.decision == "require_approval":
                approved = False
                if self._approval_gateway is not None:
                    if request.approval_token is not None:
                        token_validation = self._approval_gateway.validate_token(
                            token_id=request.approval_token,
                            request=request,
                        )
                        if token_validation.valid:
                            consume_result = self._approval_gateway.consume_token(
                                token_id=request.approval_token,
                                request=request,
                            )
                            if consume_result.valid:
                                approved = True
                                self._append_audit_event(
                                    request=request,
                                    decision="allow",
                                    reason_code="APPROVAL_TOKEN_ACCEPTED",
                                    details={"approval_token": request.approval_token},
                                )
                            else:
                                self._append_audit_event(
                                    request=request,
                                    decision="deny",
                                    reason_code=consume_result.reason_code or "POLICY_DENIED",
                                    details={"approval_token": request.approval_token},
                                )
                                response = ToolCallResponseV1(
                                    request_id=request.request_id,
                                    status="denied",
                                    error=ToolCallErrorV1(
                                        code=consume_result.reason_code or "POLICY_DENIED",
                                        message="Approval token was rejected.",
                                        retryable=False,
                                        details={
                                            "approval_token": request.approval_token,
                                            "policy_snapshot_id": policy_decision.policy_snapshot_id,
                                        },
                                    ),
                                )
                                self._append_lifecycle_event(
                                    run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response
                                )
                                return response
                        else:
                            self._append_audit_event(
                                request=request,
                                decision="deny",
                                reason_code=token_validation.reason_code or "POLICY_DENIED",
                                details={"approval_token": request.approval_token},
                            )
                            response = ToolCallResponseV1(
                                request_id=request.request_id,
                                status="denied",
                                error=ToolCallErrorV1(
                                    code=token_validation.reason_code or "POLICY_DENIED",
                                    message="Approval token was rejected.",
                                    retryable=False,
                                    details={
                                        "approval_token": request.approval_token,
                                        "policy_snapshot_id": policy_decision.policy_snapshot_id,
                                    },
                                ),
                            )
                            self._append_lifecycle_event(
                                run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response
                            )
                            return response
                    else:
                        record = self._approval_gateway.request(request)
                        if record.status is ApprovalStatus.DENIED:
                            self._append_audit_event(
                                request=request,
                                decision="deny",
                                reason_code="APPROVAL_DENIED",
                                details={"approval_id": record.approval_id},
                            )
                            response = ToolCallResponseV1(
                                request_id=request.request_id,
                                status="denied",
                                error=ToolCallErrorV1(
                                    code="POLICY_DENIED",
                                    message="Approval decision is denied.",
                                    retryable=False,
                                    details={
                                        "approval_id": record.approval_id,
                                        "policy_snapshot_id": policy_decision.policy_snapshot_id,
                                    },
                                ),
                            )
                            self._append_lifecycle_event(
                                run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response
                            )
                            return response
                        self._append_audit_event(
                            request=request,
                            decision="require_approval",
                            reason_code=policy_decision.reason_code,
                            details={"approval_id": record.approval_id},
                        )
                        self._append_approval_requested_event(run_dir, request, approval_id=record.approval_id)
                        response = ToolCallResponseV1(
                            request_id=request.request_id,
                            status="approval_required",
                            error=ToolCallErrorV1(
                                code="APPROVAL_REQUIRED",
                                message=f"Approval required by policy ({policy_decision.reason_code}).",
                                retryable=False,
                                details={
                                    "policy_snapshot_id": policy_decision.policy_snapshot_id,
                                    "approval_id": record.approval_id,
                                },
                            ),
                        )
                        self._append_lifecycle_event(
                            run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response
                        )
                        return response
                if not approved:
                    self._append_audit_event(
                        request=request,
                        decision="require_approval",
                        reason_code=policy_decision.reason_code,
                    )
                    response = ToolCallResponseV1(
                        request_id=request.request_id,
                        status="approval_required",
                        error=ToolCallErrorV1(
                            code="APPROVAL_REQUIRED",
                            message=f"Approval required by policy ({policy_decision.reason_code}).",
                            retryable=False,
                            details={"policy_snapshot_id": policy_decision.policy_snapshot_id},
                        ),
                    )
                    self._append_lifecycle_event(run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response)
                    return response

        operation = self._tool_spec.operation_by_id(request.operation)
        if operation is None:
            self._append_audit_event(
                request=request,
                decision="deny",
                reason_code="INVALID_REQUEST",
            )
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
            self._append_audit_event(
                request=request,
                decision="deny",
                reason_code=capability_error.code,
            )
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
            self._append_audit_event(
                request=request,
                decision="deny",
                reason_code=schema_error.code,
            )
            response = ToolCallResponseV1(
                request_id=request.request_id,
                status="error",
                error=schema_error,
            )
            self._append_lifecycle_event(run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response)
            return response

        if self._policy_engine is not None:
            constraint_decision = self._policy_engine.evaluate_constraints(
                agent_id=request.agent_id,
                operation=request.operation,
                input_payload=request.input,
            )
            if constraint_decision.decision == "deny":
                self._append_audit_event(
                    request=request,
                    decision="deny",
                    reason_code=constraint_decision.reason_code,
                )
                response = ToolCallResponseV1(
                    request_id=request.request_id,
                    status="denied",
                    error=ToolCallErrorV1(
                        code=constraint_decision.reason_code,
                        message=f"Denied by operation constraints ({constraint_decision.reason_code}).",
                        retryable=False,
                        details={"policy_snapshot_id": constraint_decision.policy_snapshot_id},
                    ),
                )
                self._append_lifecycle_event(run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response)
                return response

            rate_limit_decision = self._policy_engine.evaluate_rate_limit(
                agent_id=request.agent_id,
                operation=request.operation,
                request_id=request.request_id,
            )
            if rate_limit_decision.decision == "deny":
                self._append_audit_event(
                    request=request,
                    decision="deny",
                    reason_code=rate_limit_decision.reason_code,
                )
                response = ToolCallResponseV1(
                    request_id=request.request_id,
                    status="denied",
                    error=ToolCallErrorV1(
                        code=rate_limit_decision.reason_code,
                        message=f"Denied by rate limit ({rate_limit_decision.reason_code}).",
                        retryable=False,
                        details={"policy_snapshot_id": rate_limit_decision.policy_snapshot_id},
                    ),
                )
                self._append_lifecycle_event(run_dir, request, RunEventType.TOOL_CALL_COMPLETED, response)
                return response

        response = self._invoke_with_retry(request=request, operation=operation)
        self._append_audit_event(
            request=request,
            decision="allow" if response.status == "ok" else "deny",
            reason_code="EXECUTED" if response.status == "ok" else (response.error.code if response.error else "UPSTREAM_ERROR"),
        )
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
                mapped_error = map_connector_exception(exc)
                if not mapped_error.retryable:
                    return ToolCallResponseV1(
                        request_id=request.request_id,
                        status="denied" if mapped_error.code == "POLICY_DENIED" else "error",
                        error=mapped_error,
                    )
                last_error = mapped_error
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
        allowed_capabilities: list[str] | None,
    ) -> ToolCallErrorV1 | None:
        if allowed_capabilities is None:
            allowed = {request.capability}
        else:
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
            "input": redact_sensitive_data(request.input),
        }
        if request.trace.causation_id is not None:
            payload["causation_id"] = request.trace.causation_id
        if response is not None:
            payload["status"] = response.status
            if response.error is not None:
                payload["error_code"] = response.error.code
                payload["error_message"] = response.error.message
                payload["error_details"] = redact_sensitive_data(response.error.details)
        event = create_run_event(
            run_id=request.run_id,
            event_type=event_type,
            step_id=request.node_id,
            payload=payload,
        )
        append_run_event(run_dir, event)

    def _append_approval_requested_event(
        self,
        run_dir: Path,
        request: ToolCallRequestV1,
        *,
        approval_id: str,
    ) -> None:
        event = create_run_event(
            run_id=request.run_id,
            event_type=RunEventType.APPROVAL_REQUESTED,
            step_id=request.node_id,
            payload={
                "approval_id": approval_id,
                "request_id": request.request_id,
                "agent_id": request.agent_id,
                "operation": request.operation,
                "capability": request.capability,
                "correlation_id": request.trace.correlation_id,
                "input": redact_sensitive_data(request.input),
            },
        )
        append_run_event(run_dir, event)

    def _append_audit_event(
        self,
        *,
        request: ToolCallRequestV1,
        decision: str,
        reason_code: str,
        details: dict[str, object] | None = None,
    ) -> None:
        event = create_audit_event(
            actor=request.agent_id,
            run_id=request.run_id,
            request_id=request.request_id,
            decision=decision,
            reason_code=reason_code,
            details=details
            or {
                "operation": request.operation,
                "capability": request.capability,
            },
        )
        append_audit_event(self._runs_root, event)
