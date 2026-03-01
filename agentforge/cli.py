"""Minimal command-line interface for AgentForge."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agentforge.contracts.models import Mode, TriggerKind, TriggerSpec
from agentforge.orchestrator.runner import run_pipeline


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
            raise RuntimeError("dispatch command is not implemented yet")

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
