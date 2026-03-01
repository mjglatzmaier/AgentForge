from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from agentforge.contracts.models import ExecutionRequest, ExecutionStatus
from agents.arxiv_research import entrypoint


def _request(
    *,
    tmp_path: Path,
    operation: str,
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
            "config": {"mode": "replay"},
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
        return {"outputs": [], "metrics": {"count": 2}}

    monkeypatch.setattr(entrypoint, "fetch_and_snapshot", _stub)
    request = _request(tmp_path=tmp_path, operation="fetch_and_snapshot")

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.metrics["count"] == 2
    assert called["ctx"]["step_id"] == "node-1"


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
    digest_path.write_text("{}", encoding="utf-8")

    monkeypatch.setattr(
        entrypoint,
        "render_report",
        lambda _ctx: {"outputs": [], "metrics": {"highlights": 0}},
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


def test_run_supports_local_write_delivery_stub(tmp_path: Path) -> None:
    request = _request(tmp_path=tmp_path, operation="local_write_delivery")

    result = entrypoint.run(request)

    assert result.status is ExecutionStatus.SUCCESS
    assert result.metrics["delivery"] == "stub"
    assert (tmp_path / "steps" / "00_node-1" / "outputs").is_dir()


def test_run_rejects_unknown_operation(tmp_path: Path) -> None:
    request = _request(tmp_path=tmp_path, operation="unknown_operation")
    with pytest.raises(ValueError, match="Unsupported plugin operation"):
        entrypoint.run(request)
