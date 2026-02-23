from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from agentforge.contracts.models import ArtifactRef, Mode, RunConfig


def test_run_config_valid_construction() -> None:
    run_config = RunConfig(
        run_id="run-001",
        timestamp=datetime(2026, 2, 23, 0, 0, tzinfo=timezone.utc),
        mode=Mode.PROD,
        pipeline_name="research_digest",
    )

    assert run_config.run_id == "run-001"
    assert run_config.mode is Mode.PROD
    assert run_config.git_sha is None


def test_artifact_ref_valid_construction() -> None:
    artifact = ArtifactRef(
        name="docs_json",
        type="json",
        path="runs/run-001/steps/00_fetch/outputs/docs.json",
        sha256="abc123",
        producer_step_id="fetch_docs",
    )

    assert artifact.name == "docs_json"
    assert artifact.producer_step_id == "fetch_docs"


def test_missing_required_fields_rejected() -> None:
    with pytest.raises(ValidationError):
        RunConfig(
            timestamp=datetime(2026, 2, 23, 0, 0, tzinfo=timezone.utc),
            mode=Mode.DEBUG,
            pipeline_name="research_digest",
        )

    with pytest.raises(ValidationError):
        ArtifactRef(
            name="digest_md",
            type="markdown",
            path="runs/run-001/steps/04_render/outputs/digest.md",
            sha256="def456",
        )


def test_run_config_timestamp_must_be_timezone_aware() -> None:
    with pytest.raises(ValidationError):
        RunConfig(
            run_id="run-002",
            timestamp=datetime(2026, 2, 23, 0, 0),
            mode=Mode.EVAL,
            pipeline_name="research_digest",
        )

    parsed = RunConfig(
        run_id="run-003",
        timestamp="2026-02-23T00:00:00+00:00",
        mode=Mode.EVAL,
        pipeline_name="research_digest",
    )
    assert parsed.timestamp.tzinfo is not None
