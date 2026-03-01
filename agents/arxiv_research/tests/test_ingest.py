from __future__ import annotations

import json
from pathlib import Path

import pytest

from agents.arxiv_research import ingest


class _FakeResponse:
    def __init__(self, text: str) -> None:
        self.text = text

    def raise_for_status(self) -> None:
        return None


_FEED_XML = """
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title> Agent Test One </title>
    <summary> First summary. </summary>
    <published>2026-01-01T00:00:00Z</published>
    <author><name>Alice</name></author>
    <category term="cs.AI" />
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00002v1</id>
    <title>Agent Test Two</title>
    <summary>Second summary.</summary>
    <published>2026-01-02T00:00:00Z</published>
    <author><name>Bob</name></author>
    <category term="cs.LG" />
  </entry>
</feed>
""".strip()


def test_live_mode_fetches_feed_and_writes_snapshots(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(ingest.httpx, "get", lambda *args, **kwargs: _FakeResponse(_FEED_XML))

    result = ingest.fetch_and_snapshot(
        {
            "step_dir": str(tmp_path),
            "config": {"query": "cat:cs.AI", "max_results": 2, "mode": "live"},
        }
    )

    assert [output["name"] for output in result["outputs"]] == ["raw_feed_xml", "papers_raw"]
    assert (tmp_path / "outputs" / "raw_feed.xml").read_text(encoding="utf-8") == _FEED_XML
    papers = json.loads((tmp_path / "outputs" / "papers_raw.json").read_text(encoding="utf-8"))
    assert len(papers) == 2
    assert papers[0]["paper_id"] == "2401.00001v1"
    assert papers[1]["paper_id"] == "2401.00002v1"
    assert result["metrics"]["count"] == 2


def test_replay_mode_uses_snapshot_inputs_without_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snapshot_dir = tmp_path / "snapshot"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    raw_feed = snapshot_dir / "raw_feed.xml"
    papers_raw = snapshot_dir / "papers_raw.json"
    raw_feed.write_text(_FEED_XML, encoding="utf-8")
    papers_raw.write_text(
        json.dumps(
            [
                {
                    "paper_id": "2401.00001v1",
                    "title": "Agent Test One",
                    "authors": ["Alice"],
                    "abstract": "First summary.",
                    "categories": ["cs.AI"],
                    "published": "2026-01-01T00:00:00Z",
                }
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        ingest.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should not be called")),
    )

    result = ingest.fetch_and_snapshot(
        {
            "step_dir": str(tmp_path),
            "config": {"query": "cat:cs.AI", "max_results": 1, "mode": "replay"},
            "inputs": {
                "raw_feed_xml": {"abs_path": str(raw_feed)},
                "papers_raw": {"abs_path": str(papers_raw)},
            },
        }
    )

    assert [output["name"] for output in result["outputs"]] == ["raw_feed_xml", "papers_raw"]
    assert (tmp_path / "outputs" / "raw_feed.xml").read_text(encoding="utf-8") == _FEED_XML
    replay_papers = json.loads((tmp_path / "outputs" / "papers_raw.json").read_text(encoding="utf-8"))
    assert replay_papers[0]["paper_id"] == "2401.00001v1"


def test_replay_mode_requires_snapshot_inputs(tmp_path: Path) -> None:
    raw_feed = tmp_path / "raw_feed.xml"
    raw_feed.write_text(_FEED_XML, encoding="utf-8")
    with pytest.raises(KeyError, match="papers_raw"):
        ingest.fetch_and_snapshot(
            {
                "step_dir": str(tmp_path),
                "config": {"query": "cat:cs.AI", "max_results": 1, "mode": "replay"},
                "inputs": {"raw_feed_xml": {"abs_path": str(raw_feed)}},
            }
        )


def test_live_mode_normalizes_to_deterministic_paper_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    unordered_xml = """
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2401.00002v1</id>
    <title>Paper Two</title>
    <summary>Second summary.</summary>
    <published>2026-01-02T00:00:00Z</published>
    <author><name>Bob</name></author>
    <category term="cs.LG" />
  </entry>
  <entry>
    <id>http://arxiv.org/abs/2401.00001v1</id>
    <title>Paper One</title>
    <summary>First summary.</summary>
    <published>2026-01-01T00:00:00Z</published>
    <author><name>Alice</name></author>
    <category term="cs.AI" />
  </entry>
</feed>
""".strip()
    monkeypatch.setattr(ingest.httpx, "get", lambda *args, **kwargs: _FakeResponse(unordered_xml))

    ingest.fetch_and_snapshot(
        {
            "step_dir": str(tmp_path),
            "config": {"query": "cat:cs.AI", "max_results": 2, "mode": "live"},
        }
    )
    papers = json.loads((tmp_path / "outputs" / "papers_raw.json").read_text(encoding="utf-8"))
    assert [paper["paper_id"] for paper in papers] == ["2401.00001v1", "2401.00002v1"]
