"""Minimal command-line interface for AgentForge."""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from agentforge.contracts.models import ArtifactRef, Mode, TriggerKind, TriggerSpec
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
            _build_trigger_spec(args)
            run_id = _persist_dispatch_request_artifact(
                request_path=Path(args.request),
                base_dir=Path(args.base_dir),
            )
            raise RuntimeError(f"dispatch command is not implemented yet (run_id={run_id})")

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


def _persist_dispatch_request_artifact(*, request_path: Path, base_dir: Path) -> str:
    if not request_path.exists():
        raise FileNotFoundError(f"Request file not found: {request_path}")
    if not request_path.is_file():
        raise ValueError(f"Request path must be a file: {request_path}")

    run_id = str(uuid4())
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
    return run_id
