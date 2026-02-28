from __future__ import annotations

import json
from pathlib import Path

from agents.research_digest.src import steps


def test_normalize_wrapper_writes_expected_output_and_contract(tmp_path: Path) -> None:
    arxiv_docs = [
        {
            "title": "Doc B",
            "authors": ["Alice"],
            "abstract": "b",
            "url": "https://example.com/b",
            "published": "2026-01-02",
        },
        {
            "title": "Doc A",
            "authors": ["Bob"],
            "abstract": "a",
            "url": "https://example.com/a",
            "published": "2026-01-01",
        },
    ]
    rss_docs = [
        {
            "title": "Doc C",
            "url": "https://example.com/c",
            "snippet": "c",
            "published": "2026-01-03",
        }
    ]
    arxiv_path = tmp_path / "docs_arxiv.json"
    rss_path = tmp_path / "docs_rss.json"
    arxiv_path.write_text(json.dumps(arxiv_docs), encoding="utf-8")
    rss_path.write_text(json.dumps(rss_docs), encoding="utf-8")

    step_dir = tmp_path / "normalize_step"
    result = steps.normalize(
        {
            "step_dir": str(step_dir),
            "inputs": {
                "docs_arxiv": {"abs_path": str(arxiv_path)},
                "docs_rss": {"abs_path": str(rss_path)},
            },
            "config": {"max_docs": 2},
        }
    )

    assert set(result.keys()) == {"outputs", "metrics"}
    assert [item["name"] for item in result["outputs"]] == ["docs_normalized"]
    output_path = result["outputs"][0]["path"]
    assert output_path.startswith("outputs/")
    assert ".." not in output_path
    assert not output_path.startswith("/")

    written = step_dir / output_path
    assert written.is_file()
    payload = json.loads(written.read_text(encoding="utf-8"))
    assert len(payload) == 2
    assert [item["url"] for item in payload] == ["https://example.com/a", "https://example.com/b"]
