"""Control-plane artifact handoff validation utilities."""

from __future__ import annotations

from typing import Sequence

from agentforge.contracts.models import ArtifactRef, ControlNode, Manifest


def resolve_node_inputs_from_manifest(node: ControlNode, manifest: Manifest) -> dict[str, ArtifactRef]:
    """Resolve node inputs strictly by logical artifact name from manifest."""

    resolved: dict[str, ArtifactRef] = {}
    for input_name in node.inputs:
        try:
            resolved[input_name] = manifest.require_artifact(input_name)
        except KeyError as exc:
            raise KeyError(
                f"Node '{node.node_id}' requires missing manifest artifact '{input_name}'."
            ) from exc
    return resolved


def validate_ingest_snapshot_artifacts(
    node: ControlNode,
    produced_artifacts: Sequence[ArtifactRef],
) -> None:
    """Require ingest nodes to emit at least one snapshot artifact."""

    if not _is_ingest_operation(node.operation):
        return
    if any(_is_snapshot_artifact(artifact) for artifact in produced_artifacts):
        return
    raise ValueError(
        f"Ingest node '{node.node_id}' must produce at least one snapshot artifact."
    )


def _is_ingest_operation(operation: str) -> bool:
    normalized = operation.strip().lower()
    return normalized == "ingest" or normalized.startswith("ingest.")


def _is_snapshot_artifact(artifact: ArtifactRef) -> bool:
    artifact_type = artifact.type.strip().lower()
    artifact_name = artifact.name.strip().lower()
    return artifact_type == "snapshot" or "snapshot" in artifact_name
