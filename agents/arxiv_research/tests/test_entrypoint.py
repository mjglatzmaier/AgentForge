from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from agentforge.contracts.models import ExecutionRequest, ExecutionStatus
from agents.arxiv_research import entrypoint


def _request(
    *,
    tmp_path: Path,
    operation: str,
    mode: str = "replay",
    inputs: list[str] | None = None,
    input_artifacts: dict[str, Any] | None = None,
) -> ExecutionRequest:
    return ExecutionRequest(
        run_id="run-001",
        node_id="node-1",
        agent_id="arxiv.research",
        operation=operation,
        runtime="python",
        inputs=list(inputs or []),
        timeout_s=30.0,
        metadata={
            "run_dir": str(tmp_path),
            "step_dir": str(tmp_path / "steps" / "00_node-1"),
            "config": {"mode": mode},
            "input_artifacts": dict(input_artifacts or {}),
        },
    )


def _artifact_payload(*, name: str, path: str) -> dict[str, str]:
    return {
        "name": name,
        "type": "json",
        "path": path,
        "sha256": "a" * 64,
        "producer_step_id": "producer",
    }


def test_run_dispatches_fetch_and_snapshot(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    called: dict[str, Any] = {}

    def _stub(ctx: dict[str, Any]) -> dict[str, Any]:
        called["ctx"] = ctx
        outputs_dir = Path(ctx["step_dir"]) / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        out_path = outputs_dir / "raw_feed.xml"
        out_path.write_text("<feed />", encoding="utf-8")
        return {
            "outputs": [{"name": "raw_feed_xml", "type": "xml", "path": "outputs/raw_feed.xml"}],
            "metrics": {"count": 2},
        }

    monkeypatch.setattr(entrypoint, "fetch_and_snapshot", _stub)
    request = _request(tmp_path=tmp_path, operation="fetch_and_snapshot", mode="live")

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.metrics["count"] == 2
    assert called["ctx"]["step_id"] == "node-1"
    assert len(result.produced_artifacts) == 1
    artifact = result.produced_artifacts[0]
    assert artifact.name == "raw_feed_xml"
    assert artifact.path == "outputs/raw_feed.xml"
    assert artifact.producer_step_id == "node-1"
    assert len(artifact.sha256) == 64


def test_run_dispatches_synthesize_digest_with_resolved_input_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "snapshots" / "papers_raw.json"
    papers_path.parent.mkdir(parents=True, exist_ok=True)
    papers_path.write_text("[]", encoding="utf-8")
    called: dict[str, Any] = {}

    def _stub(ctx: dict[str, Any]) -> dict[str, Any]:
        called["ctx"] = ctx
        return {"outputs": [], "metrics": {"papers": 0}}

    monkeypatch.setattr(entrypoint, "synthesize_digest", _stub)
    request = _request(
        tmp_path=tmp_path,
        operation="synthesize_digest",
        inputs=["papers_raw"],
        input_artifacts={
            "papers_raw": _artifact_payload(name="papers_raw", path="snapshots/papers_raw.json")
        },
    )

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.metrics["papers"] == 0
    assert called["ctx"]["inputs"]["papers_raw"]["abs_path"] == str(papers_path.resolve())


def test_run_dispatches_render_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    digest_path = tmp_path / "steps" / "01_prior" / "outputs" / "digest.json"
    digest_path.parent.mkdir(parents=True, exist_ok=True)
    digest_path.write_text(json.dumps({"query": "q", "generated_at_utc": "2026-01-01T00:00:00Z", "papers": [], "highlights": []}), encoding="utf-8")

    monkeypatch.setattr(
        entrypoint,
        "render_report",
        lambda ctx: _render_stub(ctx),
    )
    request = _request(
        tmp_path=tmp_path,
        operation="render_report",
        inputs=["digest_json"],
        input_artifacts={
            "digest_json": _artifact_payload(
                name="digest_json", path="steps/01_prior/outputs/digest.json"
            )
        },
    )

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.metrics["highlights"] == 0
    assert {artifact.name for artifact in result.produced_artifacts} == {
        "report_md",
        "sources_json",
    }


def test_run_supports_local_write_delivery_stub(tmp_path: Path) -> None:
    request = _request(tmp_path=tmp_path, operation="local_write_delivery")

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.metrics["delivery"] == "stub"
    assert (tmp_path / "steps" / "00_node-1" / "outputs").is_dir()


def test_run_rejects_unknown_operation(tmp_path: Path) -> None:
    request = _request(tmp_path=tmp_path, operation="unknown_operation")
    result = entrypoint.run(request)
    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert "Unsupported plugin operation" in result.error
    assert result.produced_artifacts == []


def test_run_returns_failed_without_partial_outputs_when_operation_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _stub(ctx: dict[str, Any]) -> dict[str, Any]:
        outputs_dir = Path(ctx["step_dir"]) / "outputs"
        outputs_dir.mkdir(parents=True, exist_ok=True)
        (outputs_dir / "partial.txt").write_text("partial", encoding="utf-8")
        raise RuntimeError("boom")

    monkeypatch.setattr(entrypoint, "fetch_and_snapshot", _stub)
    request = _request(tmp_path=tmp_path, operation="fetch_and_snapshot", mode="live")

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error == "boom"
    assert result.produced_artifacts == []


def test_run_rejects_non_outputs_relative_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def _stub(_ctx: dict[str, Any]) -> dict[str, Any]:
        return {
            "outputs": [{"name": "bad", "type": "text", "path": "tmp/bad.txt"}],
            "metrics": {},
        }

    monkeypatch.setattr(entrypoint, "fetch_and_snapshot", _stub)
    request = _request(tmp_path=tmp_path, operation="fetch_and_snapshot", mode="live")

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert "must start with 'outputs/'" in result.error


def test_run_validates_required_inputs_for_operation(tmp_path: Path) -> None:
    request = _request(tmp_path=tmp_path, operation="synthesize_digest", mode="replay")

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert "requires manifest input artifact" in result.error


def test_run_requires_snapshot_inputs_for_fetch_replay_before_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        entrypoint,
        "fetch_and_snapshot",
        lambda _ctx: (_ for _ in ()).throw(AssertionError("should not execute")),
    )
    request = _request(tmp_path=tmp_path, operation="fetch_and_snapshot", mode="replay")

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert "raw_feed_xml" in result.error
    assert "papers_raw" in result.error


def test_run_rejects_unsupported_mode_with_explicit_error(tmp_path: Path) -> None:
    request = _request(tmp_path=tmp_path, operation="synthesize_digest", mode="sandbox")

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error is not None
    assert "Unsupported mode" in result.error


def test_run_maps_failed_operation_payload_to_failed_execution_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    papers_path = tmp_path / "snapshots" / "papers_raw.json"
    papers_path.parent.mkdir(parents=True, exist_ok=True)
    papers_path.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(
        entrypoint,
        "synthesize_digest",
        lambda _ctx: {"status": "failed", "error": "provider timeout", "metrics": {"provider": "openai"}},
    )
    request = _request(
        tmp_path=tmp_path,
        operation="synthesize_digest",
        mode="replay",
        inputs=["papers_raw"],
        input_artifacts={
            "papers_raw": _artifact_payload(name="papers_raw", path="snapshots/papers_raw.json")
        },
    )

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.FAILED
    assert result.error == "provider timeout"
    assert result.metrics["provider"] == "openai"
    assert result.produced_artifacts == []


def _render_stub(ctx: dict[str, Any]) -> dict[str, Any]:
    outputs_dir = Path(ctx["step_dir"]) / "outputs"
    outputs_dir.mkdir(parents=True, exist_ok=True)
    (outputs_dir / "digest.json").write_text("{}", encoding="utf-8")
    (outputs_dir / "report.md").write_text("# Report", encoding="utf-8")
    (outputs_dir / "sources.json").write_text("[]", encoding="utf-8")
    return {
        "outputs": [
            {"name": "digest_json", "type": "json", "path": "outputs/digest.json"},
            {"name": "report_md", "type": "markdown", "path": "outputs/report.md"},
            {"name": "sources_json", "type": "json", "path": "outputs/sources.json"},
        ],
        "metrics": {"highlights": 0},
    }
