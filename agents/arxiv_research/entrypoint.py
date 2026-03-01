from __future__ import annotations

from pathlib import Path
from typing import Any

from agentforge.control.plugin_contract import dispatch_plugin_operation
from agentforge.contracts.models import ArtifactRef, ExecutionRequest, ExecutionResult, ExecutionStatus
from agents.arxiv_research.ingest import fetch_and_snapshot
from agents.arxiv_research.render import render_report
from agents.arxiv_research.synthesis import synthesize_digest

_ADAPTER = "arxiv-plugin"
_ADAPTER_VERSION = "1"


def run(request: ExecutionRequest) -> ExecutionResult:
    return dispatch_plugin_operation(
        request,
        operations={
            "fetch_and_snapshot": _run_fetch_and_snapshot,
            "synthesize_digest": _run_synthesize_digest,
            "render_report": _run_render_report,
            "local_write_delivery": _run_local_write_delivery,
        },
    )


def _run_fetch_and_snapshot(request: ExecutionRequest) -> ExecutionResult:
    payload = fetch_and_snapshot(_request_context(request))
    return _success_result(payload)


def _run_synthesize_digest(request: ExecutionRequest) -> ExecutionResult:
    payload = synthesize_digest(_request_context(request))
    return _success_result(payload)


def _run_render_report(request: ExecutionRequest) -> ExecutionResult:
    payload = render_report(_request_context(request))
    return _success_result(payload)


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


def _success_result(step_payload: dict[str, Any]) -> ExecutionResult:
    metrics = step_payload.get("metrics", {})
    if not isinstance(metrics, dict):
        raise TypeError("Step payload metrics must be a mapping.")
    return ExecutionResult(
        status=ExecutionStatus.SUCCESS,
        metrics=metrics,
        adapter=_ADAPTER,
        adapter_version=_ADAPTER_VERSION,
    )


def _required_metadata_str(request: ExecutionRequest, key: str) -> str:
    value = request.metadata.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"ExecutionRequest metadata.{key} must be a non-empty string.")
    return value.strip()
