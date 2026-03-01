from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentforge.providers import LlmResult, ProviderValidationError
from agents.arxiv_research import synthesis
from agents.arxiv_research.models import DigestBullet, ResearchPaper, SynthesisHighlights


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
    def __init__(self, highlights: SynthesisHighlights) -> None:
        self.highlights = highlights
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, **kwargs: Any) -> LlmResult[SynthesisHighlights]:
        self.calls.append(dict(kwargs))
        return LlmResult(
            parsed=self.highlights,
            raw_text=self.highlights.model_dump_json(),
            provider="stub",
            model=str(kwargs.get("model", "stub-model")),
        )


class _FailingProviderStub:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.calls = 0

    def generate_json(self, **kwargs: Any) -> LlmResult[SynthesisHighlights]:
        self.calls += 1
        raise self.error


class _RetryProviderStub:
    def __init__(self, *, failure_error: Exception, success_payload: SynthesisHighlights) -> None:
        self.failure_error = failure_error
        self.success_payload = success_payload
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, **kwargs: Any) -> LlmResult[SynthesisHighlights]:
        self.calls.append(dict(kwargs))
        if len(self.calls) == 1:
            raise self.failure_error
        return LlmResult(
            parsed=self.success_payload,
            raw_text=self.success_payload.model_dump_json(),
            provider="stub",
            model=str(kwargs.get("model", "stub-model")),
        )


def test_synthesize_digest_prefers_selected_input_when_available(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    selected_payload = [
        {
            "paper_id": "selected-1",
            "title": "Selected Paper",
            "authors": ["Alice"],
            "abstract": "Selected abstract",
            "categories": ["cs.AI"],
            "published": "2026-01-01T00:00:00Z",
        }
    ]
    raw_payload = [
        {
            "paper_id": "raw-1",
            "title": "Raw Paper",
            "authors": ["Bob"],
            "abstract": "Raw abstract",
            "categories": ["cs.LG"],
            "published": "2026-01-02T00:00:00Z",
        }
    ]
    selected_path = tmp_path / "papers_selected.json"
    raw_path = tmp_path / "papers_raw.json"
    selected_path.write_text(json.dumps(selected_payload), encoding="utf-8")
    raw_path.write_text(json.dumps(raw_payload), encoding="utf-8")

    highlights = SynthesisHighlights(
        query="agent systems",
        highlights=[DigestBullet(text="Selected-only citation", cited_paper_ids=["selected-1"])],
    )
    provider = _ProviderStub(highlights)
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: provider)

    result = synthesis.synthesize_digest(
        {
            "step_dir": str(tmp_path),
            "inputs": {
                "papers_selected": {"abs_path": str(selected_path)},
                "papers_raw": {"abs_path": str(raw_path)},
            },
            "config": {"mode": "replay"},
        }
    )

    assert result["metrics"]["papers"] == 1


def test_synthesize_digest_falls_back_to_raw_input(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    highlights = SynthesisHighlights(
        query="agent systems",
        highlights=[DigestBullet(text="Raw fallback citation", cited_paper_ids=["2401.00001v1"])],
    )
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: _ProviderStub(highlights))

    result = synthesis.synthesize_digest(
        {
            "step_dir": str(tmp_path),
            "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
            "config": {"mode": "replay"},
        }
    )

    assert result["metrics"]["papers"] == 2


def test_synthesize_digest_uses_provider_and_writes_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    highlights = SynthesisHighlights(
        query="agent systems",
        highlights=[DigestBullet(text="Key contribution", cited_paper_ids=["2401.00001v1"])],
    )
    provider = _ProviderStub(highlights)
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

    assert [item["name"] for item in result["outputs"]] == ["digest_json", "synthesis_diagnostics"]
    output_payload = json.loads((tmp_path / "outputs" / "digest.json").read_text(encoding="utf-8"))
    assert output_payload["papers"][0]["paper_id"] == "2401.00001v1"
    assert output_payload["highlights"][0]["cited_paper_ids"] == ["2401.00001v1"]
    diagnostics_payload = json.loads(
        (tmp_path / "outputs" / "synthesis_diagnostics.json").read_text(encoding="utf-8")
    )
    assert diagnostics_payload["status"] == "success"
    assert diagnostics_payload["overflow_detected"] is False
    assert diagnostics_payload["finish_reason"] is None
    assert diagnostics_payload["error"] is None
    assert diagnostics_payload["prompt_chars"] > 0
    assert diagnostics_payload["est_prompt_tokens"] > 0
    assert diagnostics_payload["retry_count"] == 0
    assert diagnostics_payload["retry_outcome"] == "not_needed"
    assert diagnostics_payload["applied_limits"]["max_highlights"] == 5
    assert diagnostics_payload["applied_limits"]["paper_limit"] == 2
    assert provider.calls
    call = provider.calls[0]
    assert call["response_model"] is SynthesisHighlights
    assert "Summarize key contributions" in call["prompt"]
    assert "Input compressed papers JSON" in call["prompt"]
    assert "cited_paper_ids" in call["prompt"]
    assert '"abstract_snippet"' in call["prompt"]
    assert '"authors"' not in call["prompt"]


def test_synthesize_digest_rejects_uncited_highlights(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    highlights = SynthesisHighlights(
        query="agent systems",
        highlights=[DigestBullet(text="Missing citation", cited_paper_ids=[])],
    )
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: _ProviderStub(highlights))

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
    highlights = SynthesisHighlights(
        query="agent systems",
        highlights=[DigestBullet(text="Bad citation", cited_paper_ids=["unknown-id"])],
    )
    provider = _ProviderStub(highlights)
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: provider)

    with pytest.raises(ProviderValidationError, match="unknown cited_paper_ids"):
        synthesis.synthesize_digest(
            {
                "step_dir": str(tmp_path),
                "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
                "config": {"mode": "live"},
            }
        )
    assert len(provider.calls) == 1


def test_synthesize_digest_replay_mode_uses_deterministic_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    highlights = SynthesisHighlights(
        query="agent systems",
        highlights=[DigestBullet(text="Replay citation", cited_paper_ids=["2401.00001v1"])],
    )
    provider = _ProviderStub(highlights)
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


def test_synthesize_digest_writes_failure_diagnostics_on_provider_validation_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    error = ProviderValidationError(
        "openai response failed schema validation; raw excerpt: {\"highlights\": [}. "
        "finish_reason=length. tail_excerpt={\"highlights\": [}"
    )
    provider = _FailingProviderStub(error)
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: provider)

    with pytest.raises(ProviderValidationError, match="finish_reason=length"):
        synthesis.synthesize_digest(
            {
                "step_dir": str(tmp_path),
                "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
                "config": {"mode": "live"},
            }
        )

    diagnostics_payload = json.loads(
        (tmp_path / "outputs" / "synthesis_diagnostics.json").read_text(encoding="utf-8")
    )
    assert diagnostics_payload["status"] == "failed"
    assert diagnostics_payload["finish_reason"] == "length"
    assert diagnostics_payload["overflow_detected"] is True
    assert diagnostics_payload["retry_count"] == 1
    assert diagnostics_payload["retry_outcome"] == "exhausted"
    assert "finish_reason=length" in diagnostics_payload["error"]
    assert provider.calls == 2


def test_synthesize_digest_uses_config_query_when_llm_query_is_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    highlights = SynthesisHighlights(
        query=None,
        highlights=[DigestBullet(text="Config fallback citation", cited_paper_ids=["2401.00001v1"])],
    )
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: _ProviderStub(highlights))

    synthesis.synthesize_digest(
        {
            "step_dir": str(tmp_path),
            "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
            "config": {"mode": "replay", "query": "fallback query"},
        }
    )

    output_payload = json.loads((tmp_path / "outputs" / "digest.json").read_text(encoding="utf-8"))
    assert output_payload["query"] == "fallback query"


def test_replay_mode_produces_identical_digest_for_same_snapshot_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    highlights = SynthesisHighlights(
        query="agent systems",
        highlights=[DigestBullet(text="Replay citation", cited_paper_ids=["2401.00001v1"])],
    )
    provider = _ProviderStub(highlights)
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


def test_compress_papers_for_prompt_enforces_bounds_and_fields() -> None:
    papers = [
        ResearchPaper.model_validate(
            {
                "paper_id": "b-paper",
                "title": "B" * 20,
                "authors": ["Bob"],
                "abstract": "beta abstract " * 20,
                "categories": ["cs.LG", "cs.AI"],
                "published": "2026-01-02T00:00:00Z",
            }
        ),
        ResearchPaper.model_validate(
            {
                "paper_id": "a-paper",
                "title": "A" * 20,
                "authors": ["Alice"],
                "abstract": "alpha abstract " * 20,
                "categories": ["cs.CL"],
                "published": "2026-01-01T00:00:00Z",
            }
        ),
    ]
    compressed = synthesis._compress_papers_for_prompt(
        papers,
        title_max_chars=10,
        abstract_snippet_chars=30,
        paper_limit=10,
    )

    assert [item["paper_id"] for item in compressed] == ["a-paper", "b-paper"]
    assert set(compressed[0].keys()) == {
        "paper_id",
        "title",
        "published",
        "categories",
        "abstract_snippet",
    }
    assert len(compressed[0]["title"]) <= 10
    assert len(compressed[0]["abstract_snippet"]) <= 30
    assert compressed[1]["categories"] == ["cs.AI", "cs.LG"]


def test_compress_papers_for_prompt_is_deterministic() -> None:
    papers = [ResearchPaper.model_validate(item) for item in _papers_payload()]
    first = synthesis._compress_papers_for_prompt(
        papers,
        title_max_chars=180,
        abstract_snippet_chars=600,
        paper_limit=10,
    )
    second = synthesis._compress_papers_for_prompt(
        list(reversed(papers)),
        title_max_chars=180,
        abstract_snippet_chars=600,
        paper_limit=10,
    )
    assert first == second


def test_synthesize_digest_applies_budget_limits_deterministically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = _papers_payload()
    payload[0]["abstract"] = "A" * 4000
    payload[1]["abstract"] = "B" * 4000
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(payload), encoding="utf-8")
    highlights = SynthesisHighlights(
        query="agent systems",
        highlights=[DigestBullet(text="Budget citation", cited_paper_ids=["2401.00001v1"])],
    )
    provider = _ProviderStub(highlights)
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: provider)

    synthesis.synthesize_digest(
        {
            "step_dir": str(tmp_path),
            "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
            "config": {
                "mode": "replay",
                "max_input_tokens_est": 300,
                "reserved_output_tokens": 0,
            },
        }
    )

    diagnostics_payload = json.loads(
        (tmp_path / "outputs" / "synthesis_diagnostics.json").read_text(encoding="utf-8")
    )
    assert diagnostics_payload["applied_limits"]["abstract_snippet_chars"] < 600
    assert diagnostics_payload["est_prompt_tokens"] <= 300


def test_synthesize_digest_retries_once_for_overflow_like_validation_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "papers_raw.json"
    papers_path.write_text(json.dumps(_papers_payload()), encoding="utf-8")
    provider = _RetryProviderStub(
        failure_error=ProviderValidationError("schema failure. finish_reason=length. tail_excerpt={"),
        success_payload=SynthesisHighlights(
            query="agent systems",
            highlights=[DigestBullet(text="Recovered citation", cited_paper_ids=["2401.00001v1"])],
        ),
    )
    monkeypatch.setattr(synthesis, "_resolve_provider", lambda _ctx: provider)

    synthesis.synthesize_digest(
        {
            "step_dir": str(tmp_path),
            "inputs": {"papers_raw": {"abs_path": str(papers_path)}},
            "config": {"mode": "replay"},
        }
    )

    diagnostics_payload = json.loads(
        (tmp_path / "outputs" / "synthesis_diagnostics.json").read_text(encoding="utf-8")
    )
    assert len(provider.calls) == 2
    assert diagnostics_payload["status"] == "success"
    assert diagnostics_payload["retry_count"] == 1
    assert diagnostics_payload["retry_outcome"] == "recovered"
    first_prompt = str(provider.calls[0]["prompt"])
    second_prompt = str(provider.calls[1]["prompt"])
    assert first_prompt != second_prompt
