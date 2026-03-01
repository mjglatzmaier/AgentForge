from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path


def _write_dispatch_plugin(base_dir: Path, *, module_name: str, status: str = "success") -> None:
    plugin_path = base_dir / f"{module_name}.py"
    if status == "success":
        plugin_path.write_text(
            """
import hashlib
import json
from pathlib import Path

def run(request):
    outputs_dir = Path(request.metadata["outputs_dir"])
    outputs_dir.mkdir(parents=True, exist_ok=True)
    file_name = f"{request.operation}.json"
    file_path = outputs_dir / file_name
    file_path.write_text(json.dumps({"ok": True, "operation": request.operation}), encoding="utf-8")
    return {
        "status": "success",
        "produced_artifacts": [
            {
                "name": f"{request.operation}_result",
                "type": "json",
                "path": f"outputs/{file_name}",
                "sha256": hashlib.sha256(file_path.read_bytes()).hexdigest(),
                "producer_step_id": request.node_id,
            }
        ],
    }
""".strip(),
            encoding="utf-8",
        )
        return
    plugin_path.write_text(
        """
def run(request):
    return {"status": "failed", "error": "simulated runtime failure"}
""".strip(),
        encoding="utf-8",
    )


def _write_dispatch_agent(
    base_dir: Path,
    *,
    agent_id: str = "arxiv.research",
    module_name: str = "dispatch_test_plugin",
) -> None:
    agent_yaml = base_dir / "agents" / "arxiv_research" / "agent.yaml"
    agent_yaml.parent.mkdir(parents=True, exist_ok=True)
    agent_yaml.write_text(
        f"""
agent_id: {agent_id}
version: 1.0.0
description: test
intents: [research]
tags: [digest]
input_contracts: [Req]
output_contracts: [Res]
runtime:
  runtime: python
  type: python_subprocess
  entrypoint: {module_name}:run
  timeout_s: 30
  max_concurrency: 1
capabilities:
  operations:
    - name: pipeline
      inputs: [request_json]
      outputs: [pipeline_result]
    - name: fetch_and_snapshot
      inputs: [request_json]
      outputs: [raw_feed_xml, papers_raw]
operations_policy:
  terminal_access: none
  allowed_commands: []
  fs_scope: [.]
  network_access: none
  network_allowlist: []
""".strip(),
        encoding="utf-8",
    )


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
            "arxiv.research",
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
    _write_dispatch_plugin(tmp_path, module_name="dispatch_test_plugin", status="success")
    _write_dispatch_agent(tmp_path)
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "dispatch",
            "--agent",
            "arxiv.research",
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
    assert completed.returncode == 0
    run_id = completed.stdout.strip()
    assert run_id
    run_dirs = [path for path in (tmp_path / "runs").iterdir() if path.name != ".cache"]
    assert len(run_dirs) == 1
    run_dir = run_dirs[0]
    assert run_dir.name == run_id
    request_copy = run_dir / "control" / "inputs" / "request.json"
    assert request_copy.read_text(encoding="utf-8") == "{}"

    manifest_payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["run_id"] == run_dir.name
    artifacts = manifest_payload["artifacts"]
    artifact_names = {artifact["name"] for artifact in artifacts}
    assert "request_json" in artifact_names
    assert "pipeline_result" in artifact_names
    plan_payload = json.loads((run_dir / "control" / "plan.json").read_text(encoding="utf-8"))
    trigger_payload = json.loads((run_dir / "control" / "trigger.json").read_text(encoding="utf-8"))
    registry_payload = json.loads((run_dir / "control" / "registry.json").read_text(encoding="utf-8"))
    snapshot_payload = json.loads((run_dir / "control" / "snapshot.json").read_text(encoding="utf-8"))
    assert plan_payload["plan_id"] == f"dispatch-{run_dir.name}"
    assert len(plan_payload["nodes"]) == 1
    assert plan_payload["nodes"][0]["agent_id"] == "arxiv.research"
    assert plan_payload["nodes"][0]["operation"] == "pipeline"
    assert plan_payload["nodes"][0]["inputs"] == ["request_json"]
    assert trigger_payload["request_artifact"] == "request_json"
    assert trigger_payload["metadata"]["agent_id"] == "arxiv.research"
    assert registry_payload["schema_version"] == 1
    assert "agents" in registry_payload
    assert snapshot_payload["node_states"]["dispatch_node"] == "succeeded"
    assert (run_dir / "steps" / "00_dispatch_node" / "outputs" / "pipeline.json").is_file()


def test_cli_dispatch_accepts_event_trigger_kind(tmp_path: Path) -> None:
    _write_dispatch_plugin(tmp_path, module_name="dispatch_test_plugin", status="success")
    _write_dispatch_agent(tmp_path)
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "dispatch",
            "--agent",
            "arxiv.research",
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
    assert completed.returncode == 0
    run_dirs = [path for path in (tmp_path / "runs").iterdir() if path.name != ".cache"]
    assert len(run_dirs) == 1
    trigger_payload = json.loads((run_dirs[0] / "control" / "trigger.json").read_text(encoding="utf-8"))
    assert trigger_payload["kind"] == "event"
    assert trigger_payload["event_type"] == "webhook.github"


def test_cli_dispatch_supports_plan_override_file(tmp_path: Path) -> None:
    _write_dispatch_plugin(tmp_path, module_name="dispatch_test_plugin", status="success")
    _write_dispatch_agent(tmp_path)
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")
    plan_file = tmp_path / "plan_override.yaml"
    plan_file.write_text(
        """
plan_id: override-plan
max_parallel: 1
trigger:
  kind: manual
  source: tests
nodes:
  - node_id: fetch
    agent_id: arxiv.research
    operation: fetch_and_snapshot
    inputs: [request_json]
    outputs: [raw_feed_xml, papers_raw]
""".strip(),
        encoding="utf-8",
    )
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "dispatch",
            "--agent",
            "arxiv.research",
            "--request",
            str(request_file),
            "--plan",
            str(plan_file),
            "--base-dir",
            str(tmp_path),
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    run_dirs = [path for path in (tmp_path / "runs").iterdir() if path.name != ".cache"]
    assert len(run_dirs) == 1
    plan_payload = json.loads((run_dirs[0] / "control" / "plan.json").read_text(encoding="utf-8"))
    assert plan_payload["plan_id"] == "override-plan"
    assert [node["node_id"] for node in plan_payload["nodes"]] == ["fetch"]
    assert plan_payload["nodes"][0]["agent_id"] == "arxiv.research"
    assert plan_payload["nodes"][0]["operation"] == "fetch_and_snapshot"
    assert plan_payload["trigger"]["request_artifact"] == "request_json"
    assert (run_dirs[0] / "steps" / "00_fetch" / "outputs" / "fetch_and_snapshot.json").is_file()


def test_cli_dispatch_rejects_unknown_agent_before_run_start(tmp_path: Path) -> None:
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "dispatch",
            "--agent",
            "agent.missing",
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
    assert completed.returncode == 1
    assert "Unknown agent_id for dispatch" in completed.stderr
    assert not (tmp_path / "runs").exists()


def test_cli_dispatch_runtime_failure_uses_exit_code_two_with_concise_error(tmp_path: Path) -> None:
    _write_dispatch_plugin(tmp_path, module_name="dispatch_fail_plugin", status="failed")
    _write_dispatch_agent(tmp_path, module_name="dispatch_fail_plugin")
    request_file = tmp_path / "request.json"
    request_file.write_text("{}", encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "agentforge",
            "dispatch",
            "--agent",
            "arxiv.research",
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
    assert "dispatch failed (run_id=" in completed.stderr
    assert "node_id=dispatch_node" in completed.stderr


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
