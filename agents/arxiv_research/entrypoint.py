from __future__ import annotations

import re
from pathlib import PurePosixPath
from pathlib import Path
from typing import Any

from agentforge.control.plugin_contract import dispatch_plugin_operation
from agentforge.contracts.models import ArtifactRef, ExecutionRequest, ExecutionResult, ExecutionStatus
from agentforge.storage.hashing import sha256_file
from agents.arxiv_research.ingest import fetch_and_snapshot
from agents.arxiv_research.render import render_report
from agents.arxiv_research.synthesis import synthesize_digest

_ADAPTER = "arxiv-plugin"
_ADAPTER_VERSION = "1"
_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def run(request: ExecutionRequest) -> ExecutionResult:
    try:
        _validate_operation_contract(request)
        return dispatch_plugin_operation(
            request,
            operations={
                "fetch_and_snapshot": _run_fetch_and_snapshot,
                "synthesize_digest": _run_synthesize_digest,
                "render_report": _run_render_report,
                "local_write_delivery": _run_local_write_delivery,
            },
        )
    except Exception as exc:
        return _failure_result(error=str(exc), traceback_excerpt=type(exc).__name__)


def _run_fetch_and_snapshot(request: ExecutionRequest) -> ExecutionResult:
    return _execute_step_operation(request, fetch_and_snapshot)


def _run_synthesize_digest(request: ExecutionRequest) -> ExecutionResult:
    return _execute_step_operation(request, synthesize_digest)


def _run_render_report(request: ExecutionRequest) -> ExecutionResult:
    return _execute_step_operation(request, render_report)


def _run_local_write_delivery(request: ExecutionRequest) -> ExecutionResult:
    step_dir = Path(_required_metadata_str(request, "step_dir"))
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    return ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        metrics={"delivery": "stub"},
        adapter=_ADAPTER,
        adapter_version=_ADAPTER_VERSION,
    )


def _execute_step_operation(
    request: ExecutionRequest, operation: Any
) -> ExecutionResult:
    try:
        payload = operation(_request_context(request))
    except Exception as exc:
        return _failure_result(error=str(exc), traceback_excerpt=type(exc).__name__)

    if not isinstance(payload, dict):
        raise TypeError("Operation payload must be a mapping.")

    metrics = payload.get("metrics", {})
    if not isinstance(metrics, dict):
        raise TypeError("Step payload metrics must be a mapping.")

    status = str(payload.get("status", "success")).strip().lower()
    if status == ExecutionStatus.FAILED.value:
        error = payload.get("error")
        error_text = str(error).strip() if error is not None else "Operation failed."
        return _failure_result(error=error_text, metrics=metrics)
    if status != ExecutionStatus.SUCCESS.value:
        raise ValueError(f"Unsupported operation payload status: {status}")

    outputs = payload.get("outputs", [])
    if not isinstance(outputs, list):
        raise TypeError("Step payload outputs must be a list.")
    outputs = _filter_passthrough_outputs(outputs=outputs, input_names=set(request.inputs))

    produced_artifacts = _build_produced_artifacts(
        request=request,
        outputs=outputs,
    )
    return ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        produced_artifacts=produced_artifacts,
        metrics=metrics,
        adapter=_ADAPTER,
        adapter_version=_ADAPTER_VERSION,
    )


def _request_context(request: ExecutionRequest) -> dict[str, Any]:
    run_dir = _required_metadata_str(request, "run_dir")
    step_dir = _required_metadata_str(request, "step_dir")
    config = request.metadata.get("config", {})
    if not isinstance(config, dict):
        raise TypeError("ExecutionRequest metadata.config must be a mapping when provided.")

    return {
        "run_id": request.run_id,
        "step_id": request.node_id,
        "step_dir": step_dir,
        "config": dict(config),
        "inputs": _context_inputs(request=request, run_dir=Path(run_dir)),
    }


def _context_inputs(*, request: ExecutionRequest, run_dir: Path) -> dict[str, dict[str, str]]:
    raw_inputs = request.metadata.get("input_artifacts", {})
    if not isinstance(raw_inputs, dict):
        raise TypeError("ExecutionRequest metadata.input_artifacts must be a mapping when provided.")

    resolved: dict[str, dict[str, str]] = {}
    for input_name in request.inputs:
        artifact = ArtifactRef.model_validate(raw_inputs[input_name])
        artifact_path = Path(artifact.path)
        abs_path = artifact_path if artifact_path.is_absolute() else (run_dir / artifact_path)
        resolved[input_name] = {
            "name": artifact.name,
            "type": artifact.type,
            "path": artifact.path,
            "sha256": artifact.sha256,
            "producer_step_id": artifact.producer_step_id,
            "abs_path": str(abs_path.resolve()),
        }
    return resolved


def _build_produced_artifacts(
    *,
    request: ExecutionRequest,
    outputs: list[dict[str, Any]],
) -> list[ArtifactRef]:
    step_dir = Path(_required_metadata_str(request, "step_dir"))
    produced: list[ArtifactRef] = []
    for output in outputs:
        if not isinstance(output, dict):
            raise TypeError("Each output entry must be a mapping.")
        name = _required_output_field(output, "name")
        artifact_type = _required_output_field(output, "type")
        normalized_path = _normalize_output_path(_required_output_field(output, "path"))
        file_path = step_dir / normalized_path
        if not file_path.is_file():
            raise ValueError(f"Output artifact file does not exist: {normalized_path}")
        produced.append(
            ArtifactRef(
                name=name,
                type=artifact_type,
                path=normalized_path,
                sha256=sha256_file(file_path),
                producer_step_id=request.node_id,
            )
        )
    return produced


def _filter_passthrough_outputs(
    *,
    outputs: list[dict[str, Any]],
    input_names: set[str],
) -> list[dict[str, Any]]:
    if not input_names:
        return outputs
    filtered: list[dict[str, Any]] = []
    for output in outputs:
        if not isinstance(output, dict):
            filtered.append(output)
            continue
        raw_name = output.get("name")
        if isinstance(raw_name, str) and raw_name.strip() in input_names:
            continue
        filtered.append(output)
    return filtered


def _required_output_field(output: dict[str, Any], key: str) -> str:
    value = output.get(key)
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"Output field '{key}' must be a non-empty string.")
    return value.strip()


def _normalize_output_path(path: str) -> str:
    normalized = path.replace("\\", "/").strip()
    if normalized.startswith("/") or _WINDOWS_DRIVE_PREFIX.match(normalized):
        raise ValueError("Output artifact path must be relative.")
    posix = PurePosixPath(normalized)
    if ".." in posix.parts:
        raise ValueError("Output artifact path must not contain '..'.")
    if not normalized.startswith("outputs/"):
        raise ValueError("Output artifact path must start with 'outputs/'.")
    return posix.as_posix()


def _failure_result(
    *,
    error: str,
    traceback_excerpt: str | None = None,
    metrics: dict[str, Any] | None = None,
) -> ExecutionResult:
    return ExecutionResult(
        status=ExecutionStatus.FAILED,
        produced_artifacts=[],
        metrics=dict(metrics or {}),
        error=error,
        traceback_excerpt=traceback_excerpt,
        adapter=_ADAPTER,
        adapter_version=_ADAPTER_VERSION,
    )


def _required_metadata_str(request: ExecutionRequest, key: str) -> str:
    value = request.metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"ExecutionRequest metadata.{key} must be a non-empty string.")
    return value.strip()


def _validate_operation_contract(request: ExecutionRequest) -> None:
    operation = request.operation.strip()
    mode = _mode_from_request(request)

    required_inputs: set[str] = set()
    if operation == "synthesize_digest":
        required_inputs = {"papers_raw"}
    elif operation == "render_report":
        required_inputs = {"digest_json"}
    elif operation == "fetch_and_snapshot" and mode == "replay":
        required_inputs = {"raw_feed_xml", "papers_raw"}

    missing = sorted(required_inputs - set(request.inputs))
    if missing:
        raise ValueError(
            f"Operation '{operation}' requires manifest input artifact(s): {missing}."
        )


def _mode_from_request(request: ExecutionRequest) -> str:
    config = request.metadata.get("config", {})
    if not isinstance(config, dict):
        raise TypeError("ExecutionRequest metadata.config must be a mapping when provided.")
    mode = str(config.get("mode", "live")).strip().lower()
    if mode not in {"live", "replay"}:
        raise ValueError(f"Unsupported mode for arxiv plugin operation '{request.operation}': {mode}")
    return mode
