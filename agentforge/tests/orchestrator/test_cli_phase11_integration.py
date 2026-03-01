from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import agentforge.cli as cli_module
from agentforge.cli import run_cli
from agentforge.contracts.models import ArtifactRef, TriggerKind, TriggerSpec
from agentforge.providers import LlmResult
from agentforge.storage.hashing import sha256_file
from agentforge.storage.manifest import load_manifest, register_artifact, save_manifest
from agents.arxiv_research import ingest, synthesis
from agents.arxiv_research.models import ResearchDigest, SynthesisHighlights


class _ProviderStub:
    def __init__(self, digest: ResearchDigest) -> None:
        self._highlights = SynthesisHighlights(query=digest.query, highlights=digest.highlights)

    def generate_json(self, **kwargs: Any) -> LlmResult[SynthesisHighlights]:
        return LlmResult(
            parsed=self._highlights,
            raw_text=self._highlights.model_dump_json(),
            provider="stub",
            model=str(kwargs.get("model", "stub-model")),
        )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write_seed_snapshots_plugin(base_dir: Path, *, module_name: str = "phase11_seed_snapshots") -> None:
    plugin_path = base_dir / f"{module_name}.py"
    plugin_path.write_text(
        """
import shutil
from pathlib import Path

from agentforge.storage.hashing import sha256_file


def run(request):
    step_dir = Path(request.metadata["step_dir"])
    outputs_dir = step_dir / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)

    papers_fixture = Path(request.metadata["papers_fixture_path"])
    papers_output = outputs_dir / "papers_raw.json"
    shutil.copyfile(papers_fixture, papers_output)
    return {
        "status": "success",
        "produced_artifacts": [
            {
                "name": "papers_raw",
                "type": "json",
                "path": "outputs/papers_raw.json",
                "sha256": sha256_file(papers_output),
                "producer_step_id": request.node_id,
            }
        ],
    }
""".strip(),
        encoding="utf-8",
    )


def _write_seed_snapshots_agent(base_dir: Path, *, module_name: str = "phase11_seed_snapshots") -> None:
    agent_yaml = base_dir / "agents" / "seed_snapshots" / "agent.yaml"
    agent_yaml.parent.mkdir(parents=True, exist_ok=True)
    agent_yaml.write_text(
        f"""
agent_id: snapshot.seed
version: 1.0.0
description: Seeds replay snapshot artifacts for CLI integration tests.
intents: [seed]
tags: [snapshot]
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
    - name: seed_snapshots
      inputs: [request_json]
      outputs: [papers_raw]
operations_policy:
  terminal_access: none
  allowed_commands: []
  fs_scope: [{str(base_dir)}]
  network_access: none
  network_allowlist: []
""".strip(),
        encoding="utf-8",
    )


def _write_arxiv_agent_yaml(base_dir: Path) -> None:
    src = _repo_root() / "agents" / "arxiv_research" / "agent.yaml"
    dst = base_dir / "agents" / "arxiv_research" / "agent.yaml"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)
    content = dst.read_text(encoding="utf-8")
    content = content.replace("  fs_scope:\n    - .", f"  fs_scope:\n    - {str(base_dir)}")
    dst.write_text(content, encoding="utf-8")


def _write_replay_plan(base_dir: Path, *, papers_fixture_path: Path) -> Path:
    plan_path = base_dir / "phase11_plan.yaml"
    plan_path.write_text(
        f"""
plan_id: phase11-arxiv-replay
max_parallel: 1
trigger:
  kind: manual
  source: cli
nodes:
  - node_id: seed_papers
    agent_id: snapshot.seed
    operation: seed_snapshots
    inputs: [request_json]
    outputs: [papers_raw]
    metadata:
      papers_fixture_path: {str(papers_fixture_path)}

  - node_id: synthesize_digest
    agent_id: arxiv.research
    operation: synthesize_digest
    inputs: [papers_raw]
    outputs: [digest_json]
    depends_on: [seed_papers]
    metadata:
      config:
        mode: replay
        provider: openai

  - node_id: render_report
    agent_id: arxiv.research
    operation: render_report
    inputs: [digest_json]
    outputs: [report_md, sources_json]
    depends_on: [synthesize_digest]
""".strip(),
        encoding="utf-8",
    )
    return plan_path


def _dispatch_and_capture_run_id(
    *,
    tmp_path: Path,
    plan_path: Path,
    capsys: Any,
) -> str:
    request_path = tmp_path / "request.json"
    request_path.write_text("{}", encoding="utf-8")
    code = run_cli(
        [
            "dispatch",
            "--agent",
            "arxiv.research",
            "--request",
            str(request_path),
            "--plan",
            str(plan_path),
            "--base-dir",
            str(tmp_path),
        ]
    )
    captured = capsys.readouterr()
    assert code == 0, captured.err
    run_id = captured.out.strip()
    assert run_id
    return run_id


def _bootstrap_interrupted_run(
    *,
    tmp_path: Path,
    plan_path: Path,
    papers_fixture_path: Path,
    node_states: dict[str, str],
    run_id: str,
    add_failed_event: bool = False,
) -> Path:
    request_path = tmp_path / "request.json"
    request_path.write_text("{}", encoding="utf-8")
    created_run_id = cli_module._initialize_dispatch_run(
        agent_id="arxiv.research",
        request_path=request_path,
        base_dir=tmp_path,
        trigger=TriggerSpec(kind=TriggerKind.MANUAL, source="cli"),
        plan_path=plan_path,
    )
    if created_run_id != run_id:
        run_dir = tmp_path / "runs" / created_run_id
        target_dir = tmp_path / "runs" / run_id
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        run_dir.rename(target_dir)
        created_run_id = run_id
    run_dir = tmp_path / "runs" / created_run_id

    seed_output = run_dir / "steps" / "00_seed_papers" / "outputs" / "papers_raw.json"
    seed_output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(papers_fixture_path, seed_output)

    manifest_path = run_dir / "manifest.json"
    manifest = load_manifest(manifest_path)
    register_artifact(
        manifest,
        ArtifactRef(
            name="papers_raw",
            type="json",
            path="steps/00_seed_papers/outputs/papers_raw.json",
            sha256=sha256_file(seed_output),
            producer_step_id="seed_papers",
        ),
    )
    save_manifest(manifest_path, manifest)

    control_dir = run_dir / "control"
    (control_dir / "runtime_state.json").write_text(
        json.dumps({"schema_version": 1, "plan_id": "phase11-arxiv-replay", "node_states": node_states}),
        encoding="utf-8",
    )
    if add_failed_event:
        event_payload = {
            "schema_version": 1,
            "event_id": "evt-failed-final",
            "timestamp_utc": datetime.now(timezone.utc).isoformat(),
            "event_type": "node_failed",
            "node_id": "render_report",
            "payload": {"state": "failed", "retry_attempt": 1},
        }
        (control_dir / "events.jsonl").write_text(json.dumps(event_payload) + "\n", encoding="utf-8")
    return run_dir


def test_phase11_dispatch_replay_produces_digest_report_and_sources(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    repo_root = _repo_root()
    fixtures = repo_root / "agents" / "arxiv_research" / "tests" / "fixtures"
    papers_fixture = fixtures / "papers_raw.json"
    expected_digest = ResearchDigest.model_validate_json(
        (fixtures / "expected_digest.json").read_text(encoding="utf-8")
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(
        ingest.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should not be called")),
    )
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: _ProviderStub(expected_digest))

    _write_seed_snapshots_plugin(tmp_path)
    _write_seed_snapshots_agent(tmp_path)
    _write_arxiv_agent_yaml(tmp_path)
    plan_path = _write_replay_plan(tmp_path, papers_fixture_path=papers_fixture)

    run_id = _dispatch_and_capture_run_id(tmp_path=tmp_path, plan_path=plan_path, capsys=capsys)
    run_dir = tmp_path / "runs" / run_id

    assert (run_dir / "control" / "plan.json").is_file()
    assert (run_dir / "control" / "trigger.json").is_file()
    assert (run_dir / "control" / "registry.json").is_file()
    assert (run_dir / "control" / "snapshot.json").is_file()
    assert (run_dir / "steps" / "01_synthesize_digest" / "outputs" / "digest.json").is_file()
    assert (run_dir / "steps" / "02_render_report" / "outputs" / "digest.json").is_file()
    assert (run_dir / "steps" / "02_render_report" / "outputs" / "report.md").is_file()
    assert (run_dir / "steps" / "02_render_report" / "outputs" / "sources.json").is_file()

    manifest_payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    artifact_names = {artifact["name"] for artifact in manifest_payload["artifacts"]}
    assert {"request_json", "papers_raw", "digest_json", "report_md", "sources_json"} <= artifact_names


def test_phase11_resume_completes_interrupted_run_without_duplicate_artifacts(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    repo_root = _repo_root()
    fixtures = repo_root / "agents" / "arxiv_research" / "tests" / "fixtures"
    papers_fixture = fixtures / "papers_raw.json"
    expected_digest = ResearchDigest.model_validate_json(
        (fixtures / "expected_digest.json").read_text(encoding="utf-8")
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(
        ingest.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should not be called")),
    )
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: _ProviderStub(expected_digest))

    _write_seed_snapshots_plugin(tmp_path)
    _write_seed_snapshots_agent(tmp_path)
    _write_arxiv_agent_yaml(tmp_path)
    plan_path = _write_replay_plan(tmp_path, papers_fixture_path=papers_fixture)
    run_dir = _bootstrap_interrupted_run(
        tmp_path=tmp_path,
        plan_path=plan_path,
        papers_fixture_path=papers_fixture,
        node_states={
            "seed_papers": "succeeded",
            "synthesize_digest": "pending",
            "render_report": "pending",
        },
        run_id="run-phase11-resume",
    )

    code = run_cli(["resume", "--run_id", "run-phase11-resume", "--base-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert captured.out.strip() == "run-phase11-resume"

    manifest_payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    names = [artifact["name"] for artifact in manifest_payload["artifacts"]]
    assert len(names) == len(set(names))
    assert {"request_json", "papers_raw", "digest_json", "report_md", "sources_json"} <= set(names)
    snapshot_payload = json.loads((run_dir / "control" / "snapshot.json").read_text(encoding="utf-8"))
    assert snapshot_payload["node_states"] == {
        "render_report": "succeeded",
        "seed_papers": "succeeded",
        "synthesize_digest": "succeeded",
    }


def test_phase11_status_reports_running_failed_and_succeeded_with_consistent_artifacts(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    repo_root = _repo_root()
    fixtures = repo_root / "agents" / "arxiv_research" / "tests" / "fixtures"
    papers_fixture = fixtures / "papers_raw.json"
    expected_digest = ResearchDigest.model_validate_json(
        (fixtures / "expected_digest.json").read_text(encoding="utf-8")
    )

    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(
        ingest.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should not be called")),
    )
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: _ProviderStub(expected_digest))

    _write_seed_snapshots_plugin(tmp_path)
    _write_seed_snapshots_agent(tmp_path)
    _write_arxiv_agent_yaml(tmp_path)
    plan_path = _write_replay_plan(tmp_path, papers_fixture_path=papers_fixture)

    succeeded_run_id = _dispatch_and_capture_run_id(tmp_path=tmp_path, plan_path=plan_path, capsys=capsys)
    running_run_dir = _bootstrap_interrupted_run(
        tmp_path=tmp_path,
        plan_path=plan_path,
        papers_fixture_path=papers_fixture,
        node_states={
            "seed_papers": "succeeded",
            "synthesize_digest": "pending",
            "render_report": "pending",
        },
        run_id="run-phase11-running",
    )
    failed_run_dir = _bootstrap_interrupted_run(
        tmp_path=tmp_path,
        plan_path=plan_path,
        papers_fixture_path=papers_fixture,
        node_states={
            "seed_papers": "succeeded",
            "synthesize_digest": "failed",
            "render_report": "failed",
        },
        run_id="run-phase11-failed",
        add_failed_event=True,
    )

    assert run_cli(["status", "--run_id", succeeded_run_id, "--base-dir", str(tmp_path)]) == 0
    succeeded_payload = json.loads(capsys.readouterr().out.strip())
    assert succeeded_payload["status"] == "terminal"
    assert succeeded_payload["node_summary"] == {"succeeded": 3}
    assert succeeded_payload["artifact_count"] == 6
    succeeded_snapshot = json.loads((tmp_path / "runs" / succeeded_run_id / "control" / "snapshot.json").read_text(encoding="utf-8"))
    assert succeeded_payload["node_states"] == succeeded_snapshot["node_states"]
    succeeded_manifest = json.loads((tmp_path / "runs" / succeeded_run_id / "manifest.json").read_text(encoding="utf-8"))
    succeeded_artifacts = {artifact["name"] for artifact in succeeded_manifest["artifacts"]}
    assert {"digest_json", "report_md", "sources_json"} <= succeeded_artifacts

    assert run_cli(["status", "--run_id", "run-phase11-running", "--base-dir", str(tmp_path)]) == 0
    running_payload = json.loads(capsys.readouterr().out.strip())
    assert running_payload["status"] == "non-terminal"
    assert running_payload["node_states"] == {
        "render_report": "pending",
        "seed_papers": "succeeded",
        "synthesize_digest": "pending",
    }
    running_manifest = json.loads((running_run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {artifact["name"] for artifact in running_manifest["artifacts"]} == {"request_json", "papers_raw"}

    assert run_cli(["status", "--run_id", "run-phase11-failed", "--base-dir", str(tmp_path)]) == 0
    failed_payload = json.loads(capsys.readouterr().out.strip())
    assert failed_payload["status"] == "terminal"
    assert failed_payload["node_summary"] == {"failed": 2, "succeeded": 1}
    assert failed_payload["latest_event_id"] == "evt-failed-final"
    failed_manifest = json.loads((failed_run_dir / "manifest.json").read_text(encoding="utf-8"))
    assert {artifact["name"] for artifact in failed_manifest["artifacts"]} == {"request_json", "papers_raw"}
