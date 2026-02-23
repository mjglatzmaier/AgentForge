from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agentforge.contracts.models import (
    ArtifactRef,
    Manifest,
    StepResult,
    StepStatus,
)


def test_manifest_artifact_lookup() -> None:
    digest = ArtifactRef(
        name="digest_md",
        type="markdown",
        path="runs/run-001/steps/04_render/outputs/digest.md",
        sha256="aaa111",
        producer_step_id="render",
    )
    docs = ArtifactRef(
        name="docs_json",
        type="json",
        path="runs/run-001/steps/02_normalize/outputs/docs.json",
        sha256="bbb222",
        producer_step_id="normalize",
    )
    manifest = Manifest(run_id="run-001", artifacts=[docs, digest])

    # Compound key lookup
    assert manifest.get_artifact("render", "digest_md") == digest
    assert manifest.get_artifact("normalize", "docs_json") == docs

    # Missing cases
    assert manifest.get_artifact("render", "missing") is None
    assert manifest.get_artifact("missing_step", "digest_md") is None

    # require_artifact should succeed
    assert manifest.require_artifact("normalize", "docs_json") == docs


def test_manifest_require_artifact_raises_on_missing() -> None:
    manifest = Manifest(run_id="run-002")

    with pytest.raises(KeyError):
        manifest.require_artifact("normalize", "missing_artifact")


def test_step_result_fields_validate() -> None:
    step_result = StepResult(
        step_id="normalize",
        status=StepStatus.SUCCESS,
        started_at=datetime(2026, 2, 23, 1, 0, tzinfo=timezone.utc),
        ended_at=datetime(2026, 2, 23, 1, 1, tzinfo=timezone.utc),
        metrics={"docs": 4, "latency_sec": 0.42, "note": "ok"},
    )
    assert step_result.status is StepStatus.SUCCESS

    # Invalid status string
    with pytest.raises(ValidationError):
        StepResult(
            step_id="normalize",
            status="done",  # invalid enum
            started_at=datetime(2026, 2, 23, 1, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 2, 23, 1, 1, tzinfo=timezone.utc),
        )

    # Invalid metrics value type (list not allowed)
    with pytest.raises(ValidationError):
        StepResult(
            step_id="normalize",
            status=StepStatus.SUCCESS,
            started_at=datetime(2026, 2, 23, 1, 0, tzinfo=timezone.utc),
            ended_at=datetime(2026, 2, 23, 1, 1, tzinfo=timezone.utc),
            metrics={"bad": ["not-allowed"]},
        )