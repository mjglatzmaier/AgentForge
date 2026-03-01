from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import agentforge.cli as cli_module
from agentforge.cli import run_cli
from agentforge.contracts.models import ArtifactRef, TriggerKind, TriggerSpec
from agentforge.providers import LlmResult
from agentforge.storage.hashing import sha256_file
from agentforge.storage.manifest import load_manifest, register_artifact, save_manifest
from agents.arxiv_research import synthesis
from agents.arxiv_research.models import DigestBullet, SynthesisHighlights


class _ProviderFromPrompt:
    def generate_json(self, **kwargs: Any) -> LlmResult[SynthesisHighlights]:
        prompt = str(kwargs.get("prompt", ""))
        marker = "Input compressed papers JSON:\n"
        papers_payload: list[dict[str, Any]] = []
        if marker in prompt:
            papers_payload = json.loads(prompt.split(marker, maxsplit=1)[1])
        highlights: list[DigestBullet] = []
        if papers_payload:
            paper_id = str(papers_payload[0]["paper_id"])
            highlights = [
                DigestBullet(
                    text="Scorer smoke highlight",
                    cited_paper_ids=[paper_id],
                )
            ]
        payload = SynthesisHighlights(
            query="scorer-smoke",
            highlights=highlights,
        )
        return LlmResult(
            parsed=payload,
            raw_text=payload.model_dump_json(),
            provider="stub",
            model=str(kwargs.get("model", "stub-model")),
        )


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def _write_seed_plugin(base_dir: Path, *, module_name: str = "scorer_seed_plugin") -> None:
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


def _write_seed_agent(base_dir: Path, *, module_name: str = "scorer_seed_plugin") -> None:
    agent_yaml = base_dir / "agents" / "snapshot_seed" / "agent.yaml"
    agent_yaml.parent.mkdir(parents=True, exist_ok=True)
    agent_yaml.write_text(
        f"""
agent_id: snapshot.seed
version: 1.0.0
description: Seeds papers_raw fixtures for scorer smoke tests.
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
    - name: seed_papers
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


def _papers_payload(count: int = 15) -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for index in range(count):
        payload.append(
            {
                "paper_id": f"2401.{index:05d}v1",
                "title": f"LLM Agent Paper {index}",
                "authors": ["Alice", "Bob"],
                "abstract": "llm agent benchmark ablation theorem code github doi:10.1000/example",
                "categories": ["cs.AI", "cs.LG"],
                "published": f"2026-01-{(index % 28) + 1:02d}T00:00:00Z",
            }
        )
    return payload


def _write_plan(base_dir: Path, *, papers_fixture_path: Path) -> Path:
    plan_path = base_dir / "scorer_smoke_plan.yaml"
    plan_path.write_text(
        f"""
plan_id: scorer-smoke-plan
max_parallel: 1
trigger:
  kind: manual
  source: cli
nodes:
  - node_id: seed_papers
    agent_id: snapshot.seed
    operation: seed_papers
    inputs: [request_json]
    outputs: [papers_raw]
    metadata:
      papers_fixture_path: {str(papers_fixture_path)}

  - node_id: score_papers
    agent_id: arxiv.research
    operation: score_papers
    inputs: [papers_raw]
    outputs: [papers_scored, papers_selected, scoring_diagnostics]
    depends_on: [seed_papers]
    metadata:
      config:
        mode: replay
        scoring:
          select_m: 10
          top_k: 5
          min_score_threshold: 0.0
          topic_alignment:
            keywords: [llm, agent]

  - node_id: synthesize_digest
    agent_id: arxiv.research
    operation: synthesize_digest
    inputs: [papers_selected]
    outputs: [digest_json]
    depends_on: [score_papers]
    metadata:
      config:
        mode: replay
        provider: openai
        max_output_tokens: 200
        max_highlights: 2
        abstract_snippet_chars: 140
        max_input_tokens_est: 350
        reserved_output_tokens: 0

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


def _dispatch_and_capture_run_id(*, tmp_path: Path, plan_path: Path, capsys: Any) -> str:
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
    lines = [line.strip() for line in captured.out.splitlines() if line.strip()]
    assert lines
    return lines[-1]


def _bootstrap_interrupted_run(
    *,
    tmp_path: Path,
    plan_path: Path,
    papers_fixture_path: Path,
    run_id: str,
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

    runtime_state = {
        "schema_version": 1,
        "plan_id": "scorer-smoke-plan",
        "node_states": {
            "seed_papers": "succeeded",
            "score_papers": "pending",
            "synthesize_digest": "pending",
            "render_report": "pending",
        },
    }
    (run_dir / "control" / "runtime_state.json").write_text(
        json.dumps(runtime_state), encoding="utf-8"
    )
    return run_dir


def test_cli_scorer_dispatch_and_status_are_deterministic_and_artifact_safe(
    tmp_path: Path, monkeypatch: Any, capsys: Any
) -> None:
    papers_fixture = tmp_path / "papers_raw_large.json"
    papers_fixture.write_text(json.dumps(_papers_payload(15)), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: _ProviderFromPrompt())

    _write_seed_plugin(tmp_path)
    _write_seed_agent(tmp_path)
    _write_arxiv_agent_yaml(tmp_path)
    plan_path = _write_plan(tmp_path, papers_fixture_path=papers_fixture)

    run_id_a = _dispatch_and_capture_run_id(tmp_path=tmp_path, plan_path=plan_path, capsys=capsys)
    run_id_b = _dispatch_and_capture_run_id(tmp_path=tmp_path, plan_path=plan_path, capsys=capsys)
    run_dir_a = tmp_path / "runs" / run_id_a
    run_dir_b = tmp_path / "runs" / run_id_b

    manifest_a = json.loads((run_dir_a / "manifest.json").read_text(encoding="utf-8"))
    artifact_names_a = [artifact["name"] for artifact in manifest_a["artifacts"]]
    assert len(artifact_names_a) == len(set(artifact_names_a))
    assert {
        "papers_raw",
        "papers_scored",
        "papers_selected",
        "scoring_diagnostics",
        "digest_json",
        "report_md",
        "sources_json",
    } <= set(artifact_names_a)

    selected_a = json.loads(
        (run_dir_a / "steps" / "01_score_papers" / "outputs" / "papers_selected.json").read_text(
            encoding="utf-8"
        )
    )
    selected_b = json.loads(
        (run_dir_b / "steps" / "01_score_papers" / "outputs" / "papers_selected.json").read_text(
            encoding="utf-8"
        )
    )
    assert selected_a == selected_b

    assert run_cli(["status", "--run_id", run_id_a, "--base-dir", str(tmp_path)]) == 0
    status_payload = json.loads(capsys.readouterr().out.strip())
    assert status_payload["status"] == "terminal"
    assert status_payload["node_summary"] == {"succeeded": 4}
    synth_diag_a = json.loads(
        (
            run_dir_a / "steps" / "02_synthesize_digest" / "outputs" / "synthesis_diagnostics.json"
        ).read_text(encoding="utf-8")
    )
    assert synth_diag_a["status"] == "success"
    assert synth_diag_a["est_prompt_tokens"] <= 350
    assert synth_diag_a["retry_outcome"] in {"not_needed", "recovered"}


def test_cli_scorer_resume_completes_interrupted_run(tmp_path: Path, monkeypatch: Any, capsys: Any) -> None:
    papers_fixture = tmp_path / "papers_raw_large.json"
    papers_fixture.write_text(json.dumps(_papers_payload(15)), encoding="utf-8")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: _ProviderFromPrompt())

    _write_seed_plugin(tmp_path)
    _write_seed_agent(tmp_path)
    _write_arxiv_agent_yaml(tmp_path)
    plan_path = _write_plan(tmp_path, papers_fixture_path=papers_fixture)
    run_dir = _bootstrap_interrupted_run(
        tmp_path=tmp_path,
        plan_path=plan_path,
        papers_fixture_path=papers_fixture,
        run_id="run-scorer-resume",
    )

    code = run_cli(["resume", "--run_id", "run-scorer-resume", "--base-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert code == 0, captured.err
    assert captured.out.strip() == "run-scorer-resume"

    manifest_payload = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    names = [artifact["name"] for artifact in manifest_payload["artifacts"]]
    assert len(names) == len(set(names))
    assert {"papers_selected", "scoring_diagnostics", "digest_json", "report_md"} <= set(names)
    synth_diag = json.loads(
        (
            run_dir / "steps" / "02_synthesize_digest" / "outputs" / "synthesis_diagnostics.json"
        ).read_text(encoding="utf-8")
    )
    assert synth_diag["status"] == "success"
    assert synth_diag["est_prompt_tokens"] <= 350
