"""Sequential pipeline runner orchestration.

Runner responsibilities include run directory creation, manifest updates, and
step execution bookkeeping without agent-specific logic coupling.
"""

from __future__ import annotations

import json
import re
import shutil
import traceback
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

import yaml

from agentforge.contracts.models import ArtifactRef, Manifest, Mode, RunConfig, StepResult, StepSpec, StepStatus
from agentforge.orchestrator.cache import (
    compute_step_cache_key,
    load_cache_record,
    save_cache_record,
)
from agentforge.orchestrator.pipeline import load_pipeline
from agentforge.orchestrator.resolver import resolve_ref
from agentforge.storage.hashing import sha256_file
from agentforge.storage.manifest import init_manifest, register_artifacts, save_manifest
from agentforge.storage.run_layout import create_run_layout, create_step_dir
from agentforge.utils.logging import get_step_logger

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
    base_path = Path(base_dir)
    run_id = str(uuid4())
    layout = create_run_layout(base_path, run_id)

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
        step_logger = get_step_logger(step_dir / "logs" / "step.log")
        started_at = _utcnow()
        try:
            input_artifacts = _resolve_input_artifacts(manifest=manifest, step=step)
            cache_key = compute_step_cache_key(step=step, mode=mode, input_artifacts=input_artifacts)
            cached_outputs = _try_load_valid_cached_outputs(
                base_path=base_path,
                pipeline_name=pipeline.name,
                cache_key=cache_key,
                step=step,
                step_logger=step_logger,
            )
            if cached_outputs is not None:
                artifacts = _materialize_cached_artifacts(
                    base_path=base_path,
                    cached_outputs=cached_outputs,
                    manifest=manifest,
                    step_id=step.id,
                    step_dir=step_dir,
                    run_dir=layout.run_dir,
                )
                _assert_artifact_hashes(artifacts=artifacts, run_dir=layout.run_dir)
                step_logger.info("Cache hit for step '%s' with key=%s", step.id, cache_key)
                step_result = StepResult(
                    step_id=step.id,
                    status=StepStatus.SKIPPED,
                    started_at=started_at,
                    ended_at=_utcnow(),
                    metrics={},
                    outputs=artifacts,
                )
                manifest.steps.append(step_result)
                register_artifacts(manifest, artifacts)
                save_manifest(layout.manifest_json, manifest)
                _write_meta_json(step_dir=step_dir, payload=step_result.model_dump(mode="json"))
                continue

            step_callable = resolve_ref(step.ref)
            ctx = _build_step_context(
                input_artifacts=input_artifacts,
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
            _assert_artifact_hashes(artifacts=artifacts, run_dir=layout.run_dir)

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
            try:
                cache_outputs = _copy_outputs_into_cache(
                    artifacts=artifacts,
                    base_path=base_path,
                    cache_key=cache_key,
                    pipeline_name=pipeline.name,
                    run_dir=layout.run_dir,
                    step_id=step.id,
                )
                save_cache_record(
                    base_dir=base_path,
                    pipeline_name=pipeline.name,
                    cache_key=cache_key,
                    outputs=cache_outputs,
                )
            except Exception as cache_exc:
                step_logger.warning("Cache write skipped for step '%s': %s", step.id, cache_exc)
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
    input_artifacts: list[ArtifactRef],
    layout: Path,
    run_id: str,
    mode: Mode,
    step: StepSpec,
    step_dir: Path,
) -> dict[str, Any]:
    inputs: dict[str, dict[str, str]] = {}
    for input_name, artifact in zip(step.inputs, input_artifacts):
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


def _resolve_input_artifacts(*, manifest: Manifest, step: StepSpec) -> list[ArtifactRef]:
    input_artifacts: list[ArtifactRef] = []
    for input_name in step.inputs:
        artifact = manifest.get_latest_by_name(input_name)
        if artifact is None:
            raise KeyError(f"Input artifact not found for step '{step.id}': {input_name}")
        input_artifacts.append(artifact)
    return input_artifacts


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


def _assert_artifact_hashes(*, artifacts: list[ArtifactRef], run_dir: Path) -> None:
    for artifact in artifacts:
        artifact_file = (run_dir / artifact.path).resolve()
        actual_sha = sha256_file(artifact_file)
        if actual_sha != artifact.sha256:
            raise ValueError(
                f"Artifact sha256 mismatch for '{artifact.name}': expected {artifact.sha256}, got {actual_sha}"
            )


def _materialize_cached_artifacts(
    *,
    base_path: Path,
    cached_outputs: list[ArtifactRef],
    manifest: Manifest,
    step_id: str,
    step_dir: Path,
    run_dir: Path,
) -> list[ArtifactRef]:
    existing_names = {artifact.name for artifact in manifest.artifacts}
    artifacts: list[ArtifactRef] = []
    for cached_output in cached_outputs:
        if cached_output.name in existing_names:
            raise ValueError(f"Artifact name already registered in run: {cached_output.name}")

        source_file = (base_path / cached_output.path).resolve()
        suffix = source_file.suffix
        dest_rel = f"outputs/{cached_output.name}{suffix}"
        dest_file = step_dir.joinpath(*PurePosixPath(dest_rel).parts)
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_file, dest_file)

        run_relative_path = dest_file.resolve().relative_to(run_dir.resolve()).as_posix()
        artifacts.append(
            ArtifactRef(
                name=cached_output.name,
                type=cached_output.type,
                path=run_relative_path,
                sha256=cached_output.sha256,
                producer_step_id=step_id,
            )
        )
        existing_names.add(cached_output.name)
    return artifacts


def _copy_outputs_into_cache(
    *,
    artifacts: list[ArtifactRef],
    base_path: Path,
    cache_key: str,
    pipeline_name: str,
    run_dir: Path,
    step_id: str,
) -> list[ArtifactRef]:
    cache_dir = base_path / "runs" / ".cache" / pipeline_name / cache_key
    cache_dir.mkdir(parents=True, exist_ok=True)

    cache_outputs: list[ArtifactRef] = []
    for artifact in artifacts:
        source_file = (run_dir / artifact.path).resolve()
        suffix = source_file.suffix
        cache_file = cache_dir / f"{artifact.name}{suffix}"
        shutil.copy2(source_file, cache_file)
        cache_outputs.append(
            ArtifactRef(
                name=artifact.name,
                type=artifact.type,
                path=cache_file.resolve().relative_to(base_path.resolve()).as_posix(),
                sha256=artifact.sha256,
                producer_step_id=step_id,
            )
        )
    return cache_outputs


def _try_load_valid_cached_outputs(
    *,
    base_path: Path,
    pipeline_name: str,
    cache_key: str,
    step: StepSpec,
    step_logger: Any,
) -> list[ArtifactRef] | None:
    try:
        cached_outputs = load_cache_record(base_path, pipeline_name, cache_key)
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        step_logger.warning("Corrupted cache record for step '%s': %s", step.id, exc)
        return None

    if cached_outputs is None:
        return None

    names = [artifact.name for artifact in cached_outputs]
    if set(names) != set(step.outputs) or len(names) != len(set(names)):
        step_logger.warning("Cache record output names invalid for step '%s'", step.id)
        return None

    for cached_output in cached_outputs:
        source = (base_path / cached_output.path).resolve()
        if not source.is_file():
            step_logger.warning("Cache miss due to missing cached file for step '%s': %s", step.id, source)
            return None
        if sha256_file(source) != cached_output.sha256:
            step_logger.warning("Cache miss due to sha mismatch for step '%s': %s", step.id, source)
            return None

    return cached_outputs


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
