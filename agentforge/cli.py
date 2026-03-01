"""Minimal command-line interface for AgentForge."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from uuid import uuid4

import yaml

from agentforge.control.registry import AgentRegistry, build_registry_snapshot, load_agent_registry
from agentforge.control.runtime import ControlRunExecution, execute_control_run
from agentforge.control.state import persist_control_artifacts
from agentforge.contracts.models import (
    ArtifactRef,
    ControlNode,
    ControlPlan,
    ExecutionStatus,
    Mode,
    TriggerKind,
    TriggerSpec,
)
from agentforge.orchestrator.runner import run_pipeline
from agentforge.storage.hashing import sha256_file
from agentforge.storage.manifest import init_manifest, register_artifact, save_manifest
from agentforge.storage.run_layout import create_run_layout


class CLIValidationError(ValueError):
    """Raised when CLI arguments or inputs are invalid."""


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise CLIValidationError(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = _Parser(prog="agentforge")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run")
    run_parser.add_argument("pipeline")
    run_parser.add_argument("--mode", choices=[mode.value for mode in Mode], default=Mode.PROD.value)
    run_parser.add_argument("--base-dir", default=".")
    run_parser.add_argument(
        "--trigger-kind",
        choices=[kind.value for kind in TriggerKind],
        default=TriggerKind.MANUAL.value,
    )
    run_parser.add_argument("--schedule")
    run_parser.add_argument("--event-type")
    run_parser.add_argument("--trigger-source", default="cli")

    eval_parser = subparsers.add_parser("eval")
    eval_parser.add_argument("run_id")
    eval_parser.add_argument("--base-dir", default=".")

    dispatch_parser = subparsers.add_parser("dispatch")
    dispatch_parser.add_argument("--agent", required=True)
    dispatch_parser.add_argument("--request", required=True)
    dispatch_parser.add_argument("--base-dir", default=".")
    dispatch_parser.add_argument("--plan")
    dispatch_parser.add_argument(
        "--trigger-kind",
        choices=[kind.value for kind in TriggerKind],
        default=TriggerKind.MANUAL.value,
    )
    dispatch_parser.add_argument("--schedule")
    dispatch_parser.add_argument("--event-type")
    dispatch_parser.add_argument("--trigger-source", default="cli")

    resume_parser = subparsers.add_parser("resume")
    resume_parser.add_argument("--run_id", required=True)
    resume_parser.add_argument("--base-dir", default=".")

    status_parser = subparsers.add_parser("status")
    status_parser.add_argument("--run_id", required=True)
    status_parser.add_argument("--base-dir", default=".")

    return parser


def run_cli(argv: list[str] | None = None) -> int:
    """Execute CLI command and return process exit code."""
    parser = _build_parser()
    try:
        args = parser.parse_args(argv)

        if args.command == "run":
            _build_trigger_spec(args)
            run_id = run_pipeline(
                pipeline_path=Path(args.pipeline),
                base_dir=Path(args.base_dir),
                mode=Mode(args.mode),
            )
            print(run_id)
            return 0

        if args.command == "eval":
            raise RuntimeError("eval command is not implemented yet")

        if args.command == "dispatch":
            trigger = _build_trigger_spec(args)
            run_id = _initialize_dispatch_run(
                agent_id=args.agent,
                request_path=Path(args.request),
                base_dir=Path(args.base_dir),
                trigger=trigger,
                plan_path=Path(args.plan) if args.plan else None,
            )
            run_dir = Path(args.base_dir) / "runs" / run_id
            try:
                execution = execute_control_run(run_dir)
            except Exception as exc:  # map runtime/execution-plane failures to exit code 2
                raise RuntimeError(f"dispatch runtime failure (run_id={run_id}): {exc}") from exc
            failure_message = _dispatch_failure_message(run_id=run_id, execution=execution)
            if failure_message:
                raise RuntimeError(failure_message)
            print(run_id)
            return 0

        if args.command == "resume":
            raise RuntimeError("resume command is not implemented yet")

        if args.command == "status":
            raise RuntimeError("status command is not implemented yet")

        raise CLIValidationError(f"Unknown command: {args.command}")
    except CLIValidationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except (FileNotFoundError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except Exception as exc:  # narrow generic runtime failures to exit code 2
        print(str(exc), file=sys.stderr)
        return 2


def main() -> None:
    raise SystemExit(run_cli())


def _build_trigger_spec(args: argparse.Namespace) -> TriggerSpec:
    return TriggerSpec(
        kind=TriggerKind(args.trigger_kind),
        schedule=getattr(args, "schedule", None),
        event_type=getattr(args, "event_type", None),
        source=getattr(args, "trigger_source", None),
    )


def _initialize_dispatch_run(
    *,
    agent_id: str,
    request_path: Path,
    base_dir: Path,
    trigger: TriggerSpec,
    plan_path: Path | None,
) -> str:
    if not request_path.exists():
        raise FileNotFoundError(f"Request file not found: {request_path}")
    if not request_path.is_file():
        raise ValueError(f"Request path must be a file: {request_path}")

    registry = load_agent_registry(base_dir)

    run_id = str(uuid4())
    trigger_metadata = dict(trigger.metadata)
    trigger_metadata["agent_id"] = agent_id
    trigger_snapshot = trigger.model_copy(
        update={
            "request_artifact": "request_json",
            "metadata": trigger_metadata,
        }
    )
    if plan_path is None:
        plan = _materialize_initial_control_plan(
            run_id=run_id,
            agent_id=agent_id,
            trigger=trigger_snapshot,
        )
    else:
        plan = _load_control_plan_override(plan_path).model_copy(update={"trigger": trigger_snapshot})
    _validate_plan_agents_exist(plan=plan, agent_id=agent_id, registry=registry)

    layout = create_run_layout(base_dir, run_id)
    manifest = init_manifest(layout.manifest_json, run_id=run_id)

    dest = layout.run_dir / "control" / "inputs" / "request.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(request_path, dest)

    artifact = ArtifactRef(
        name="request_json",
        type="json",
        path=dest.resolve().relative_to(layout.run_dir.resolve()).as_posix(),
        sha256=sha256_file(dest),
        producer_step_id="dispatch_request",
    )
    register_artifact(manifest, artifact)
    save_manifest(layout.manifest_json, manifest)

    persist_control_artifacts(
        layout.run_dir,
        plan=plan,
        trigger=trigger_snapshot,
        registry=build_registry_snapshot(registry),
    )
    return run_id


def _materialize_initial_control_plan(*, run_id: str, agent_id: str, trigger: TriggerSpec) -> ControlPlan:
    return ControlPlan(
        plan_id=f"dispatch-{run_id}",
        trigger=trigger,
        max_parallel=1,
        nodes=[
            ControlNode(
                node_id="dispatch_node",
                agent_id=agent_id,
                operation="pipeline",
                inputs=["request_json"],
            )
        ],
    )


def _load_control_plan_override(path: Path) -> ControlPlan:
    if not path.exists():
        raise FileNotFoundError(f"Plan file not found: {path}")
    if not path.is_file():
        raise ValueError(f"Plan path must be a file: {path}")
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ControlPlan.model_validate(loaded)


def _validate_plan_agents_exist(*, plan: ControlPlan, agent_id: str, registry: AgentRegistry) -> None:
    if registry.get(agent_id) is None:
        raise ValueError(f"Unknown agent_id for dispatch: {agent_id}")
    missing = sorted({node.agent_id for node in plan.nodes if registry.get(node.agent_id) is None})
    if missing:
        raise ValueError(f"ControlPlan references unknown agent_id(s): {missing}")


def _dispatch_failure_message(*, run_id: str, execution: ControlRunExecution) -> str | None:
    failed_node_ids = sorted(
        node_id
        for node_id, result in execution.node_results.items()
        if result.status is ExecutionStatus.FAILED
    )
    if not failed_node_ids:
        return None
    node_id = failed_node_ids[0]
    result = execution.node_results[node_id]
    detail = result.error or result.traceback_excerpt or "execution failed"
    return f"dispatch failed (run_id={run_id}, node_id={node_id}): {detail}"
