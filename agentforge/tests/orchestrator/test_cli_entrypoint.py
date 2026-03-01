from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def test_cli_run_invocation_creates_run_directory(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline.yaml"
    pipeline.write_text(
        """
name: cli_pipeline
steps: []
""".strip(),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [sys.executable, "-m", "agentforge", "run", str(pipeline), "--mode", "prod", "--base-dir", str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )

    assert completed.returncode == 0
    run_id = completed.stdout.strip()
    run_dir = tmp_path / "runs" / run_id
    assert run_dir.is_dir()


def test_cli_run_accepts_schedule_trigger_kind(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline.yaml"
    pipeline.write_text(
        """
name: cli_pipeline
steps: []
""".strip(),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "run",
            str(pipeline),
            "--trigger-kind",
            "schedule",
            "--schedule",
            "0 * * * *",
            "--base-dir",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0


def test_cli_run_rejects_schedule_trigger_without_schedule(tmp_path: Path) -> None:
    pipeline = tmp_path / "pipeline.yaml"
    pipeline.write_text(
        """
name: cli_pipeline
steps: []
""".strip(),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "run",
            str(pipeline),
            "--trigger-kind",
            "schedule",
            "--base-dir",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1


def test_cli_dispatch_rejects_event_trigger_without_event_type(tmp_path: Path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "dispatch",
            "--agent",
            "agent.research",
            "--request",
            str(request_file),
            "--trigger-kind",
            "event",
            "--base-dir",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1


def test_cli_validation_error_uses_exit_code_one(tmp_path: Path) -> None:
    missing_pipeline = tmp_path / "missing.yaml"
    completed = subprocess.run(
        [sys.executable, "-m", "agentforge", "run", str(missing_pipeline)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 1


def test_cli_runtime_error_uses_exit_code_two(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "agentforge", "eval", "run-001", "--base-dir", str(tmp_path)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2


def test_cli_dispatch_entrypoint_uses_exit_code_two(tmp_path: Path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "dispatch",
            "--agent",
            "agent.research",
            "--request",
            str(request_file),
            "--base-dir",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    run_dirs = [path for path in (tmp_path / "runs").iterdir() if path.name != ".cache"]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    request_copy = run_dir / "control" / "inputs" / "request.json"
    assert request_copy.read_text(encoding="utf-8") == "{}"

    manifest_payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["run_id"] == run_dir.name
    artifacts = manifest_payload["artifacts"]
    assert len(artifacts) == 1
    assert artifacts[0]["name"] == "request_json"
    assert artifacts[0]["path"] == "control/inputs/request.json"


def test_cli_dispatch_accepts_event_trigger_kind(tmp_path: Path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "dispatch",
            "--agent",
            "agent.research",
            "--request",
            str(request_file),
            "--trigger-kind",
            "event",
            "--event-type",
            "webhook.github",
            "--base-dir",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2


def test_cli_resume_entrypoint_uses_exit_code_two(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "resume",
            "--run_id",
            "run-001",
            "--base-dir",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2


def test_cli_status_entrypoint_uses_exit_code_two(tmp_path: Path) -> None:
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "status",
            "--run_id",
            "run-001",
            "--base-dir",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
