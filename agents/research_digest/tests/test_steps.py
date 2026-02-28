from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentforge.providers.base import LlmResult, ProviderValidationError
from agents.research_digest.src import steps
from agents.research_digest.tools.models import Digest, DigestItem


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


def test_synthesize_digest_writes_digest_json_and_debug_files(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs = [
        {
            "doc_id": "doc-1",
            "title": "Agent Eval",
            "url": "https://example.com/1",
            "summary": "summary 1",
            "published": "2026-01-01",
            "source": "arxiv",
            "score": 2.0,
        },
        {
            "doc_id": "doc-2",
            "title": "Reasoning",
            "url": "https://example.com/2",
            "summary": "summary 2",
            "published": "2026-01-02",
            "source": "rss",
            "score": 1.0,
        },
    ]
    docs_path = tmp_path / "docs_ranked.json"
    docs_path.write_text(json.dumps(docs), encoding="utf-8")

    digest = Digest(
        generated_at="2026-01-03T00:00:00Z",
        items=[
            DigestItem(
                doc_id="doc-1",
                title="Agent Eval",
                url="https://example.com/1",
                summary="summary 1",
                source="arxiv",
                score=2.0,
                citations=["doc-1"],
            )
        ],
    )

    class _Provider:
        def generate_json(self, *args, **kwargs):
            return LlmResult(
                parsed=digest,
                raw_text=digest.model_dump_json(),
                provider="stub",
                model="stub-model",
            )

    monkeypatch.setattr(steps, "_resolve_provider", lambda _ctx: _Provider())
    step_dir = tmp_path / "synthesize"
    result = steps.synthesize_digest(
        {
            "step_dir": str(step_dir),
            "inputs": {"docs_ranked": {"abs_path": str(docs_path)}},
            "config": {"top_k": 2},
            "mode": "debug",
        }
    )

    assert [output["name"] for output in result["outputs"]] == ["digest_json"]
    assert (step_dir / "outputs" / "digest.json").is_file()
    assert (step_dir / "outputs" / "synthesis_prompt.txt").is_file()
    assert (step_dir / "outputs" / "raw_response.txt").is_file()
    digest_json = json.loads((step_dir / "outputs" / "digest.json").read_text(encoding="utf-8"))
    assert digest_json["items"][0]["citations"] == ["doc-1"]


def test_synthesize_digest_rejects_invalid_citations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    docs = [
        {
            "doc_id": "doc-1",
            "title": "Agent Eval",
            "url": "https://example.com/1",
            "summary": "summary 1",
            "published": "2026-01-01",
            "source": "arxiv",
            "score": 2.0,
        }
    ]
    docs_path = tmp_path / "docs_ranked.json"
    docs_path.write_text(json.dumps(docs), encoding="utf-8")

    digest = Digest(
        generated_at="2026-01-03T00:00:00Z",
        items=[
            DigestItem(
                doc_id="doc-1",
                title="Agent Eval",
                url="https://example.com/1",
                summary="summary 1",
                source="arxiv",
                score=2.0,
                citations=["doc-unknown"],
            )
        ],
    )

    class _Provider:
        def generate_json(self, *args, **kwargs):
            return LlmResult(
                parsed=digest,
                raw_text=digest.model_dump_json(),
                provider="stub",
                model="stub-model",
            )

    monkeypatch.setattr(steps, "_resolve_provider", lambda _ctx: _Provider())

    with pytest.raises(ProviderValidationError, match="invalid citations"):
        steps.synthesize_digest(
            {
                "step_dir": str(tmp_path / "synthesize"),
                "inputs": {"docs_ranked": {"abs_path": str(docs_path)}},
                "config": {"top_k": 1},
            }
        )


def test_verify_digest_citations_writes_report_with_failures(tmp_path: Path) -> None:
    docs = [
        {
            "doc_id": "doc-1",
            "title": "Agent Eval",
            "url": "https://example.com/1",
            "summary": "summary 1",
            "published": "2026-01-01",
            "source": "arxiv",
            "score": 2.0,
        }
    ]
    digest = {
        "title": "Research Digest",
        "generated_at": "2026-01-03T00:00:00Z",
        "items": [
            {
                "doc_id": "doc-1",
                "title": "Agent Eval",
                "url": "https://example.com/1",
                "summary": "summary 1",
                "source": "arxiv",
                "score": 2.0,
                "citations": [],
            },
            {
                "doc_id": "doc-1",
                "title": "Agent Eval 2",
                "url": "https://example.com/1b",
                "summary": "summary 2",
                "source": "arxiv",
                "score": 1.0,
                "citations": ["doc-unknown"],
            },
        ],
    }

    docs_path = tmp_path / "docs_ranked.json"
    digest_path = tmp_path / "digest.json"
    docs_path.write_text(json.dumps(docs), encoding="utf-8")
    digest_path.write_text(json.dumps(digest), encoding="utf-8")

    step_dir = tmp_path / "verify"
    result = steps.verify_digest_citations(
        {
            "step_dir": str(step_dir),
            "inputs": {
                "digest_json": {"abs_path": str(digest_path)},
                "docs_ranked": {"abs_path": str(docs_path)},
            },
        }
    )

    assert [output["name"] for output in result["outputs"]] == ["citation_report"]
    report = json.loads((step_dir / "outputs" / "citation_report.json").read_text(encoding="utf-8"))
    assert report["total_bullets"] == 2
    assert report["bullets_missing_citations"] == 1
    assert report["pass"] is False
    assert report["invalid_doc_id_citations"][0]["invalid_citations"] == ["doc-unknown"]
    assert result["metrics"]["pass"] == "false"


def test_verify_digest_citations_writes_passing_report(tmp_path: Path) -> None:
    docs = [
        {
            "doc_id": "doc-1",
            "title": "Agent Eval",
            "url": "https://example.com/1",
            "summary": "summary 1",
            "published": "2026-01-01",
            "source": "arxiv",
            "score": 2.0,
        }
    ]
    digest = {
        "title": "Research Digest",
        "generated_at": "2026-01-03T00:00:00Z",
        "items": [
            {
                "doc_id": "doc-1",
                "title": "Agent Eval",
                "url": "https://example.com/1",
                "summary": "summary 1",
                "source": "arxiv",
                "score": 2.0,
                "citations": ["doc-1"],
            }
        ],
    }

    docs_path = tmp_path / "docs_ranked.json"
    digest_path = tmp_path / "digest.json"
    docs_path.write_text(json.dumps(docs), encoding="utf-8")
    digest_path.write_text(json.dumps(digest), encoding="utf-8")

    step_dir = tmp_path / "verify_ok"
    result = steps.verify_digest_citations(
        {
            "step_dir": str(step_dir),
            "inputs": {
                "digest_json": {"abs_path": str(digest_path)},
                "docs_ranked": {"abs_path": str(docs_path)},
            },
        }
    )
    report = json.loads((step_dir / "outputs" / "citation_report.json").read_text(encoding="utf-8"))
    assert report["pass"] is True
    assert report["invalid_doc_id_citations"] == []
    assert result["metrics"]["pass"] == "true"
