from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agents.arxiv_research.models import DigestBullet, ResearchDigest, ResearchPaper
from agents.arxiv_research.render import render_report


def _digest_payload() -> dict:
    digest = ResearchDigest(
        query="agent systems",
        generated_at_utc=datetime(2026, 1, 3, tzinfo=timezone.utc),
        papers=[
            ResearchPaper(
                paper_id="2401.00001v1",
                title="Paper One",
                authors=["Alice"],
                abstract="A",
                categories=["cs.AI"],
                published="2026-01-01T00:00:00Z",
            ),
            ResearchPaper(
                paper_id="2401.00002v1",
                title="Paper Two",
                authors=["Bob"],
                abstract="B",
                categories=["cs.LG"],
                published="2026-01-02T00:00:00Z",
            ),
        ],
        highlights=[
            DigestBullet(
                text="Important finding",
                cited_paper_ids=["2401.00001v1", "2401.00002v1"],
            )
        ],
    )
    return digest.model_dump(mode="json")


def test_render_report_writes_digest_report_and_sources(tmp_path: Path) -> None:
    digest_path = tmp_path / "digest.json"
    digest_path.write_text(json.dumps(_digest_payload()), encoding="utf-8")

    result = render_report(
        {
            "step_dir": str(tmp_path),
            "inputs": {"digest_json": {"abs_path": str(digest_path)}},
        }
    )

    assert [item["name"] for item in result["outputs"]] == ["digest_json", "report_md", "sources_json"]
    assert (tmp_path / "outputs" / "digest.json").is_file()
    assert (tmp_path / "outputs" / "report.md").is_file()
    assert (tmp_path / "outputs" / "sources.json").is_file()

    report = (tmp_path / "outputs" / "report.md").read_text(encoding="utf-8")
    assert "# ArXiv Research Report" in report
    assert "Query: `agent systems`" in report
    assert "| paper_id | title | published | categories |" in report
    assert "Important finding (`2401.00001v1`, `2401.00002v1`)" in report

    sources = json.loads((tmp_path / "outputs" / "sources.json").read_text(encoding="utf-8"))
    assert [paper["paper_id"] for paper in sources] == ["2401.00001v1", "2401.00002v1"]


def test_render_report_rejects_unknown_citation_ids(tmp_path: Path) -> None:
    payload = _digest_payload()
    payload["highlights"] = [{"text": "Bad", "cited_paper_ids": ["unknown-paper-id"]}]
    digest_path = tmp_path / "digest.json"
    digest_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="unknown paper_id"):
        render_report(
            {
                "step_dir": str(tmp_path),
                "inputs": {"digest_json": {"abs_path": str(digest_path)}},
            }
        )
