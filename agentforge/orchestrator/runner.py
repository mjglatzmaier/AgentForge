"""Sequential pipeline runner orchestration.

Runner responsibilities include run directory creation, manifest updates, and
step execution bookkeeping without agent-specific logic coupling.
"""

from __future__ import annotations

import json
import re
import traceback
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

import yaml

from agentforge.contracts.models import ArtifactRef, Manifest, Mode, RunConfig, StepResult, StepSpec, StepStatus
from agentforge.orchestrator.pipeline import load_pipeline
from agentforge.orchestrator.resolver import resolve_ref
from agentforge.storage.hashing import sha256_file
from agentforge.storage.manifest import init_manifest, register_artifacts, save_manifest
from agentforge.storage.run_layout import create_run_layout, create_step_dir

_WINDOWS_DRIVE_PREFIX = re.compile(r"^[A-Za-z]:")


def validate_step_outputs(step: StepSpec, returned: dict[str, Any]) -> None:
    """Validate that returned output names match step output declarations exactly."""
    if not isinstance(returned, dict):
        raise TypeError(f"Step '{step.id}' must return a dict.")

    outputs = returned.get("outputs")
    if not isinstance(outputs, list):
        raise TypeError(f"Step '{step.id}' must return 'outputs' as a list.")

    names: list[str] = []
    for output in outputs:
        if isinstance(output, dict):
            name = output.get("name")
            if isinstance(name, str):
                names.append(name)

    expected = set(step.outputs)
    actual = set(names)
    missing = sorted(expected - actual)
    undeclared = sorted(actual - expected)
    duplicates = len(names) != len(set(names))

    if missing or undeclared or duplicates:
        parts: list[str] = []
        if missing:
            parts.append(f"missing outputs: {missing}")
        if undeclared:
            parts.append(f"undeclared outputs: {undeclared}")
        if duplicates:
            parts.append("duplicate output names")
        detail = "; ".join(parts)
        raise ValueError(f"Step '{step.id}' output contract violation: {detail}")


def run_pipeline(pipeline_path: str | Path, base_dir: str | Path, mode: Mode) -> str:
    """Run one pipeline sequentially and return generated run_id."""
    pipeline = load_pipeline(pipeline_path)
    run_id = str(uuid4())
    layout = create_run_layout(base_dir, run_id)

    run_config = RunConfig(
        run_id=run_id,
        timestamp=datetime.now(timezone.utc),
        mode=mode,
        pipeline_name=pipeline.name,
    )
    layout.run_yaml.write_text(
        yaml.safe_dump(run_config.model_dump(mode="json"), sort_keys=True),
        encoding="utf-8",
    )

    manifest = init_manifest(layout.manifest_json, run_id=run_id)
    for index, step in enumerate(pipeline.steps):
        step_dir = create_step_dir(layout, index, step.id)
        started_at = _utcnow()
        try:
            step_callable = resolve_ref(step.ref)
            ctx = _build_step_context(
                manifest=manifest,
                layout=layout.run_dir,
                run_id=run_id,
                mode=mode,
                step=step,
                step_dir=step_dir,
            )
            returned = step_callable(ctx)
            outputs_payload, metrics = _validate_step_payload(step=step, returned=returned)
            artifacts = _materialize_step_artifacts(
                outputs_payload=outputs_payload,
                manifest=manifest,
                step_id=step.id,
                step_dir=step_dir,
                run_dir=layout.run_dir,
            )

            step_result = StepResult(
                step_id=step.id,
                status=StepStatus.SUCCESS,
                started_at=started_at,
                ended_at=_utcnow(),
                metrics=metrics,
                outputs=artifacts,
            )
            manifest.steps.append(step_result)
            register_artifacts(manifest, artifacts)
            save_manifest(layout.manifest_json, manifest)
            _write_meta_json(step_dir=step_dir, payload=step_result.model_dump(mode="json"))
        except Exception as exc:
            step_result = StepResult(
                step_id=step.id,
                status=StepStatus.FAILED,
                started_at=started_at,
                ended_at=_utcnow(),
                metrics={},
                outputs=[],
            )
            manifest.steps.append(step_result)
            save_manifest(layout.manifest_json, manifest)
            meta_payload = step_result.model_dump(mode="json")
            meta_payload["error"] = {
                "type": exc.__class__.__name__,
                "message": str(exc),
                "traceback": traceback.format_exc(),
            }
            _write_meta_json(step_dir=step_dir, payload=meta_payload)
            raise RuntimeError(f"Pipeline execution failed at step '{step.id}' (run_id={run_id})") from exc

    return run_id


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _build_step_context(
    *,
    manifest: Manifest,
    layout: Path,
    run_id: str,
    mode: Mode,
    step: StepSpec,
    step_dir: Path,
) -> dict[str, Any]:
    inputs: dict[str, dict[str, str]] = {}
    for input_name in step.inputs:
        artifact = manifest.get_latest_by_name(input_name)
        if artifact is None:
            raise KeyError(f"Input artifact not found for step '{step.id}': {input_name}")
        input_abs = (layout / artifact.path).resolve()
        inputs[input_name] = {
            "name": artifact.name,
            "type": artifact.type,
            "path": artifact.path,
            "sha256": artifact.sha256,
            "producer_step_id": artifact.producer_step_id,
            "abs_path": str(input_abs),
        }

    return {
        "run_id": run_id,
        "run_dir": str(layout),
        "mode": mode.value,
        "step_id": step.id,
        "step_dir": str(step_dir),
        "config": dict(step.config),
        "inputs": inputs,
    }


def _validate_step_payload(
    *, step: StepSpec, returned: dict[str, Any]
) -> tuple[list[dict[str, str]], dict[str, int | float | str]]:
    if not isinstance(returned, dict):
        raise TypeError(f"Step '{step.id}' must return a dict.")
    if "outputs" not in returned:
        raise ValueError(f"Step '{step.id}' must return an 'outputs' field.")

    unexpected_keys = sorted(set(returned.keys()) - {"outputs", "metrics"})
    if unexpected_keys:
        raise ValueError(f"Step '{step.id}' returned unexpected keys: {unexpected_keys}")

    validate_step_outputs(step, returned)

    outputs_raw = returned["outputs"]
    if not isinstance(outputs_raw, list):
        raise TypeError(f"Step '{step.id}' must return 'outputs' as a list.")

    outputs_payload: list[dict[str, str]] = []
    for index, output in enumerate(outputs_raw):
        if not isinstance(output, dict):
            raise TypeError(f"Step '{step.id}' output at index {index} must be a dict.")
        expected_keys = {"name", "type", "path"}
        output_keys = set(output.keys())
        if output_keys != expected_keys:
            raise ValueError(
                f"Step '{step.id}' output at index {index} must have keys "
                f"{sorted(expected_keys)}, got {sorted(output_keys)}"
            )
        name = output["name"]
        output_type = output["type"]
        output_path = output["path"]
        if not all(isinstance(value, str) for value in (name, output_type, output_path)):
            raise TypeError(
                f"Step '{step.id}' output at index {index} values name/type/path must be strings."
            )
        outputs_payload.append({"name": name, "type": output_type, "path": output_path})

    metrics_raw = returned.get("metrics", {})
    if not isinstance(metrics_raw, dict):
        raise TypeError(f"Step '{step.id}' metrics must be a dict when provided.")

    metrics: dict[str, int | float | str] = {}
    for key, value in metrics_raw.items():
        if not isinstance(key, str):
            raise TypeError(f"Step '{step.id}' metric keys must be strings.")
        if not isinstance(value, (int, float, str)):
            raise TypeError(f"Step '{step.id}' metric '{key}' has invalid type: {type(value).__name__}")
        metrics[key] = value

    return outputs_payload, metrics


def _materialize_step_artifacts(
    *,
    outputs_payload: list[dict[str, str]],
    manifest: Manifest,
    step_id: str,
    step_dir: Path,
    run_dir: Path,
) -> list[ArtifactRef]:
    existing_names = {artifact.name for artifact in manifest.artifacts}
    artifacts: list[ArtifactRef] = []

    for output in outputs_payload:
        output_name = output["name"]
        if output_name in existing_names:
            raise ValueError(f"Artifact name already registered in run: {output_name}")

        output_file = _resolve_output_file(step_dir=step_dir, relative_path=output["path"])
        run_relative_path = output_file.resolve().relative_to(run_dir.resolve()).as_posix()
        artifacts.append(
            ArtifactRef(
                name=output_name,
                type=output["type"],
                path=run_relative_path,
                sha256=sha256_file(output_file),
                producer_step_id=step_id,
            )
        )
        existing_names.add(output_name)

    return artifacts


def _resolve_output_file(*, step_dir: Path, relative_path: str) -> Path:
    if not relative_path:
        raise ValueError("Step output path must be non-empty.")
    if relative_path.startswith("/") or _WINDOWS_DRIVE_PREFIX.match(relative_path):
        raise ValueError(f"Step output path must be relative: {relative_path}")
    if not relative_path.startswith("outputs/"):
        raise ValueError(f"Step output path must start with 'outputs/': {relative_path}")

    posix_path = PurePosixPath(relative_path)
    if ".." in posix_path.parts:
        raise ValueError(f"Step output path must not contain '..': {relative_path}")

    output_file = step_dir.joinpath(*posix_path.parts)
    if not output_file.is_file():
        raise FileNotFoundError(f"Step output file not found: {output_file}")
    return output_file


def _write_meta_json(*, step_dir: Path, payload: dict[str, Any]) -> None:
    (step_dir / "meta.json").write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
