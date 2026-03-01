from __future__ import annotations

import pytest

from agentforge.control.handoff import (
    resolve_node_inputs_from_manifest,
    validate_ingest_snapshot_artifacts,
)
from agentforge.contracts.models import (
    ArtifactRef,
    ControlNode,
    Manifest,
)


def _node(
    node_id: str,
    *,
    operation: str,
    inputs: list[str] | None = None,
) -> ControlNode:
    return ControlNode(
        node_id=node_id,
        agent_id="agent.test",
        operation=operation,
        inputs=list(inputs or []),
    )


def _artifact(name: str, *, artifact_type: str = "json") -> ArtifactRef:
    return ArtifactRef(
        name=name,
        type=artifact_type,
        path=f"steps/01_{name}/outputs/{name}.json",
        sha256="a" * 64,
        producer_step_id="01_node",
    )


def test_resolve_node_inputs_from_manifest_requires_manifest_refs() -> None:
    manifest = Manifest(
        run_id="run-001",
        artifacts=[_artifact("request_json"), _artifact("docs_ranked")],
    )
    node = _node(
        "node-1",
        operation="pipeline",
        inputs=["request_json", "docs_ranked"],
    )

    resolved = resolve_node_inputs_from_manifest(node, manifest)

    assert list(resolved.keys()) == ["request_json", "docs_ranked"]
    assert resolved["request_json"].name == "request_json"


def test_resolve_node_inputs_from_manifest_raises_on_missing_artifact() -> None:
    manifest = Manifest(run_id="run-001", artifacts=[_artifact("request_json")])
    node = _node("node-2", operation="pipeline", inputs=["request_json", "docs_ranked"])

    with pytest.raises(KeyError, match="requires missing manifest artifact 'docs_ranked'"):
        resolve_node_inputs_from_manifest(node, manifest)


def test_validate_ingest_snapshot_artifacts_accepts_snapshot() -> None:
    node = _node("node-ingest", operation="ingest.fetch")

    validate_ingest_snapshot_artifacts(
        node,
        [
            _artifact("papers_snapshot"),
            _artifact("docs_json"),
        ],
    )


def test_validate_ingest_snapshot_artifacts_rejects_missing_snapshot() -> None:
    node = _node("node-ingest", operation="ingest")

    with pytest.raises(ValueError, match="must produce at least one snapshot artifact"):
        validate_ingest_snapshot_artifacts(node, [_artifact("docs_json")])


def test_validate_ingest_snapshot_artifacts_ignores_non_ingest_nodes() -> None:
    node = _node("node-summarize", operation="synthesize")

    validate_ingest_snapshot_artifacts(node, [_artifact("docs_json")])
