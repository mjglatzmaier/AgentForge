from __future__ import annotations

import json
from pathlib import Path

from agentforge.contracts.models import Mode, StepStatus
from agentforge.orchestrator.runner import run_pipeline
from agentforge.storage.manifest import load_manifest
from agents.research_digest.tools import arxiv as arxiv_tool
from agents.research_digest.tools import rss as rss_tool


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_research_digest_pipeline_runs_end_to_end(tmp_path: Path, monkeypatch) -> None:
    arxiv_xml = """
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>https://arxiv.org/abs/2401.00001</id>
    <title>Agent Planning at Scale</title>
    <summary>Planning and retrieval for agents.</summary>
    <published>2026-01-03T00:00:00Z</published>
    <author><name>Alice</name></author>
  </entry>
  <entry>
    <id>https://arxiv.org/abs/2401.00002</id>
    <title>LLM Evaluation Benchmarks</title>
    <summary>Benchmark design for reasoning systems.</summary>
    <published>2026-01-01T00:00:00Z</published>
    <author><name>Bob</name></author>
  </entry>
</feed>
""".strip()
    rss_xml = """
<rss version="2.0">
  <channel>
    <item>
      <title>Retrieval News</title>
      <link>https://example.com/retrieval-news</link>
      <description>Retrieval improvements for agents.</description>
      <pubDate>Sat, 03 Jan 2026 00:00:00 GMT</pubDate>
    </item>
    <item>
      <title>Reasoning Update</title>
      <link>https://example.com/reasoning-update</link>
      <description>Reasoning techniques for evaluations.</description>
      <pubDate>Fri, 02 Jan 2026 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
""".strip()

    def _fake_get(url: str, *args, **kwargs) -> _FakeResponse:
        if "arxiv" in str(url):
            return _FakeResponse(arxiv_xml)
        return _FakeResponse(rss_xml)

    monkeypatch.setattr(arxiv_tool.httpx, "get", _fake_get)
    monkeypatch.setattr(rss_tool.httpx, "get", _fake_get)

    repo_root = Path(__file__).resolve().parents[3]
    pipeline_path = repo_root / "pipelines" / "research_digest.yaml"
    run_id = run_pipeline(pipeline_path, tmp_path, Mode.PROD)
    run_dir = tmp_path / "runs" / run_id

    assert run_dir.is_dir()
    assert [path.name for path in sorted((run_dir / "steps").iterdir())] == [
        "00_fetch_arxiv",
        "01_fetch_rss",
        "02_normalize",
        "03_dedupe_rank",
        "04_render",
    ]

    manifest = load_manifest(run_dir / "manifest.json")
    assert [step.status for step in manifest.steps] == [StepStatus.SUCCESS] * 5

    expected_artifacts = {
        "docs_arxiv",
        "docs_rss",
        "docs_normalized",
        "docs_ranked",
        "digest_json",
        "digest_md",
    }
    assert {artifact.name for artifact in manifest.artifacts} == expected_artifacts

    for step_dir in sorted((run_dir / "steps").iterdir()):
        meta = json.loads((step_dir / "meta.json").read_text(encoding="utf-8"))
        assert meta["status"] == StepStatus.SUCCESS.value

    digest_json = manifest.require_artifact("digest_json")
    digest_md = manifest.require_artifact("digest_md")
    assert (run_dir / digest_json.path).is_file()
    assert (run_dir / digest_md.path).is_file()
