from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentforge.providers import LlmResult
from agents.arxiv_research import ingest, synthesis
from agents.arxiv_research.models import ResearchDigest, SynthesisHighlights


class _ProviderStub:
    def __init__(self, highlights: SynthesisHighlights) -> None:
        self._highlights = highlights

    def generate_json(self, **kwargs: Any) -> LlmResult[SynthesisHighlights]:
        return LlmResult(
            parsed=self._highlights,
            raw_text=self._highlights.model_dump_json(),
            provider="stub",
            model=str(kwargs.get("model", "stub-model")),
        )


def test_replay_integration_matches_expected_digest_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixtures = Path(__file__).parent / "fixtures"
    raw_feed_fixture = fixtures / "raw_feed.xml"
    papers_fixture = fixtures / "papers_raw.json"
    expected_digest_fixture = fixtures / "expected_digest.json"

    monkeypatch.setattr(
        ingest.httpx,
        "get",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network should not be called in replay")),
    )

    ingest_step = tmp_path / "ingest"
    ingest.fetch_and_snapshot(
        {
            "step_dir": str(ingest_step),
            "config": {"query": "cat:cs.AI", "max_results": 2, "mode": "replay"},
            "inputs": {
                "raw_feed_xml": {"abs_path": str(raw_feed_fixture)},
                "papers_raw": {"abs_path": str(papers_fixture)},
            },
        }
    )

    expected_digest_payload = json.loads(expected_digest_fixture.read_text(encoding="utf-8"))
    expected_digest = ResearchDigest.model_validate(expected_digest_payload)
    monkeypatch.setattr(
        synthesis,
        "_resolve_provider",
        lambda _ctx: _ProviderStub(
            SynthesisHighlights(query=expected_digest.query, highlights=expected_digest.highlights)
        ),
    )

    synth_step = tmp_path / "synthesis"
    synthesis.synthesize_digest(
        {
            "step_dir": str(synth_step),
            "inputs": {"papers_raw": {"abs_path": str(ingest_step / "outputs" / "papers_raw.json")}},
            "config": {"mode": "replay"},
        }
    )

    produced_digest = json.loads((synth_step / "outputs" / "digest.json").read_text(encoding="utf-8"))
    assert produced_digest == expected_digest_payload
