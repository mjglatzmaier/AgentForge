from __future__ import annotations

import json
from pathlib import Path

from agents.research_digest.tools import arxiv, normalize, render, rss


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


def test_arxiv_fetch_parses_and_writes_output(tmp_path: Path, monkeypatch) -> None:
    xml = """
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1234.5678</id>
    <title>Agent Systems</title>
    <summary>Research on agent systems.</summary>
    <published>2026-01-01T00:00:00Z</published>
    <author><name>Alice</name></author>
  </entry>
</feed>
""".strip()
    monkeypatch.setattr(arxiv.httpx, "get", lambda *args, **kwargs: _FakeResponse(xml))

    result = arxiv.fetch({"step_dir": str(tmp_path), "config": {"query": "cat:cs.AI", "max_results": 1}})
    output = json.loads((tmp_path / "outputs" / "arxiv_docs.json").read_text(encoding="utf-8"))

    assert result["outputs"][0]["name"] == "arxiv_docs"
    assert output[0]["title"] == "Agent Systems"
    assert output[0]["authors"] == ["Alice"]


def test_rss_fetch_parses_and_writes_output(tmp_path: Path, monkeypatch) -> None:
    xml = """
<rss version="2.0">
  <channel>
    <item>
      <title>Evaluation News</title>
      <link>https://example.com/news</link>
      <description>Latest benchmark results.</description>
      <pubDate>Sat, 01 Jan 2026 00:00:00 GMT</pubDate>
    </item>
  </channel>
</rss>
""".strip()
    monkeypatch.setattr(rss.httpx, "get", lambda *args, **kwargs: _FakeResponse(xml))

    result = rss.fetch({"step_dir": str(tmp_path), "config": {"feed_urls": ["https://example.com/rss.xml"]}})
    output = json.loads((tmp_path / "outputs" / "rss_docs.json").read_text(encoding="utf-8"))

    assert result["outputs"][0]["name"] == "rss_docs"
    assert output[0]["title"] == "Evaluation News"
    assert output[0]["url"] == "https://example.com/news"


def test_normalize_and_render_pipeline_shapes(tmp_path: Path) -> None:
    arxiv_input = [
        {
            "title": "LLM Agent Planning",
            "authors": ["Alice"],
            "abstract": "Agent planning abstract",
            "url": "https://arxiv.org/abs/1",
            "published": "2026-01-01T00:00:00Z",
        }
    ]
    rss_input = [
        {
            "title": "RAG Update",
            "url": "https://example.com/rag",
            "snippet": "retrieval changes",
            "published": "2026-01-02",
        }
    ]
    arxiv_path = tmp_path / "arxiv_docs.json"
    rss_path = tmp_path / "rss_docs.json"
    arxiv_path.write_text(json.dumps(arxiv_input), encoding="utf-8")
    rss_path.write_text(json.dumps(rss_input), encoding="utf-8")

    normalize_step = tmp_path / "normalize"
    normalize_result = normalize.run(
        {
            "step_dir": str(normalize_step),
            "inputs": {
                "arxiv_docs": {"abs_path": str(arxiv_path)},
                "rss_docs": {"abs_path": str(rss_path)},
            },
        }
    )
    normalized = json.loads((normalize_step / "outputs" / "docs_norm.json").read_text(encoding="utf-8"))

    render_step = tmp_path / "render"
    ranked_path = tmp_path / "docs_ranked.json"
    ranked_path.write_text(json.dumps(normalized), encoding="utf-8")
    render_result = render.run(
        {"step_dir": str(render_step), "inputs": {"docs_ranked": {"abs_path": str(ranked_path)}}}
    )
    digest_json = json.loads((render_step / "outputs" / "digest.json").read_text(encoding="utf-8"))
    digest_md = (render_step / "outputs" / "digest.md").read_text(encoding="utf-8")

    assert normalize_result["outputs"][0]["name"] == "docs_norm"
    assert {doc["source"] for doc in normalized} == {"arxiv", "rss"}
    assert [output["name"] for output in render_result["outputs"]] == ["digest_md", "digest_json"]
    assert digest_json["title"] == "Research Digest"
    assert "# Research Digest" in digest_md
