from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

from agentforge.providers import LlmResult, ProviderValidationError
from agents.arxiv_research import synthesis
from agents.arxiv_research.models import DigestBullet, ResearchDigest, ResearchPaper


def _papers_payload() -> list[dict[str, Any]]:
    return [
        {
            "paper_id": "2401.00001v1",
            "title": "Paper One",
            "authors": ["Alice"],
            "abstract": "A",
            "categories": ["cs.AI"],
            "published": "2026-01-01T00:00:00Z",
        },
        {
            "paper_id": "2401.00002v1",
            "title": "Paper Two",
            "authors": ["Bob"],
            "abstract": "B",
            "categories": ["cs.LG"],
            "published": "2026-01-02T00:00:00Z",
        },
    ]


class _ProviderStub:
    def __init__(self, digest: ResearchDigest) -> None:
        self.digest = digest
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, **kwargs: Any) -> LlmResult[ResearchDigest]:
        self.calls.append(dict(kwargs))
        return LlmResult(
            parsed=self.digest,
            raw_text=self.digest.model_dump_json(),
            provider="stub",
            model=str(kwargs.get("model", "stub-model")),
        )


def test_synthesize_digest_uses_provider_and_writes_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    digest = ResearchDigest(
        query="agent systems",
        generated_at_utc=datetime(2026, 1, 3, tzinfo=timezone.utc),
        papers=[ResearchPaper.model_validate(item) for item in _papers_payload()],
        highlights=[DigestBullet(text="Key contribution", cited_paper_ids=["2401.00001v1"])],
    )
    provider = _ProviderStub(digest)
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: provider)

    result = synthesis.synthesize_digest(
        {
            "step_dir": str(tmp_path),
            "run_id": "run-1",
            "step_id": "synthesize",
            "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
            "config": {"mode": "live", "provider": "openai"},
        }
    )

    assert [item["name"] for item in result["outputs"]] == ["digest_json"]
    output_payload = json.loads((tmp_path / "outputs" / "digest.json").read_text(encoding="utf-8"))
    assert output_payload["highlights"][0]["cited_paper_ids"] == ["2401.00001v1"]
    assert provider.calls
    call = provider.calls[0]
    assert call["response_model"] is ResearchDigest
    assert "Summarize key contributions" in call["prompt"]
    assert "cited_paper_ids" in call["prompt"]


def test_synthesize_digest_rejects_uncited_highlights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    digest = ResearchDigest(
        query="agent systems",
        generated_at_utc=datetime(2026, 1, 3, tzinfo=timezone.utc),
        papers=[ResearchPaper.model_validate(item) for item in _papers_payload()],
        highlights=[DigestBullet(text="Missing citation", cited_paper_ids=[])],
    )
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: _ProviderStub(digest))

    with pytest.raises(ProviderValidationError, match="no cited_paper_ids"):
        synthesis.synthesize_digest(
            {
                "step_dir": str(tmp_path),
                "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
                "config": {"mode": "live"},
            }
        )


def test_synthesize_digest_rejects_unknown_cited_paper_ids(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    digest = ResearchDigest(
        query="agent systems",
        generated_at_utc=datetime(2026, 1, 3, tzinfo=timezone.utc),
        papers=[ResearchPaper.model_validate(item) for item in _papers_payload()],
        highlights=[DigestBullet(text="Bad citation", cited_paper_ids=["unknown-id"])],
    )
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: _ProviderStub(digest))

    with pytest.raises(ProviderValidationError, match="unknown cited_paper_ids"):
        synthesis.synthesize_digest(
            {
                "step_dir": str(tmp_path),
                "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
                "config": {"mode": "live"},
            }
        )


def test_synthesize_digest_replay_mode_uses_deterministic_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    digest = ResearchDigest(
        query="agent systems",
        generated_at_utc=datetime(2026, 1, 3, tzinfo=timezone.utc),
        papers=[ResearchPaper.model_validate(item) for item in _papers_payload()],
        highlights=[DigestBullet(text="Replay citation", cited_paper_ids=["2401.00001v1"])],
    )
    provider = _ProviderStub(digest)
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: provider)

    synthesis.synthesize_digest(
        {
            "step_dir": str(tmp_path),
            "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
            "config": {"mode": "replay"},
        }
    )

    assert provider.calls
    call = provider.calls[0]
    assert call["model"] == "gpt-4o-mini"
    assert call["temperature"] == 0.0
    assert call["seed"] == 0


def test_replay_mode_produces_identical_digest_for_same_snapshot_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    digest = ResearchDigest(
        query="agent systems",
        generated_at_utc=datetime(2026, 1, 3, tzinfo=timezone.utc),
        papers=[ResearchPaper.model_validate(item) for item in _papers_payload()],
        highlights=[DigestBullet(text="Replay citation", cited_paper_ids=["2401.00001v1"])],
    )
    provider = _ProviderStub(digest)
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: provider)

    run_a = tmp_path / "run_a"
    run_b = tmp_path / "run_b"
    synthesis.synthesize_digest(
        {
            "step_dir": str(run_a),
            "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
            "config": {"mode": "replay"},
        }
    )
    synthesis.synthesize_digest(
        {
            "step_dir": str(run_b),
            "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
            "config": {"mode": "replay"},
        }
    )

    digest_a = json.loads((run_a / "outputs" / "digest.json").read_text(encoding="utf-8"))
    digest_b = json.loads((run_b / "outputs" / "digest.json").read_text(encoding="utf-8"))
    assert digest_a == digest_b
