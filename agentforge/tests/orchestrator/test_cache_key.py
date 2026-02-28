from agentforge.contracts.models import ArtifactRef, Mode, StepKind, StepSpec
from agentforge.orchestrator.cache import compute_step_cache_key


def _artifact(name: str, sha: str) -> ArtifactRef:
    return ArtifactRef(
        name=name,
        type="json",
        path=f"runs/run-001/steps/00_demo/outputs/{name}.json",
        sha256=sha,
        producer_step_id="demo",
    )


def test_compute_step_cache_key_same_inputs_are_stable() -> None:
    step = StepSpec(
        id="normalize",
        kind=StepKind.TOOL,
        ref="agents.research_digest.tools.normalize:run",
        inputs=["docs"],
        outputs=["docs_norm"],
        config={"top_k": 10, "region": "us"},
    )
    artifacts_a = [_artifact("docs", "aaa"), _artifact("aux", "bbb")]
    artifacts_b = [_artifact("aux", "bbb"), _artifact("docs", "aaa")]

    key_a = compute_step_cache_key(step, Mode.PROD, artifacts_a)
    key_b = compute_step_cache_key(step, Mode.PROD, artifacts_b)

    assert key_a == key_b


def test_compute_step_cache_key_changes_when_config_changes() -> None:
    step_a = StepSpec(
        id="rank",
        kind=StepKind.TOOL,
        ref="agents.research_digest.tools.dedupe_rank:run",
        inputs=["docs_norm"],
        outputs=["docs_ranked"],
        config={"limit": 5},
    )
    step_b = StepSpec(
        id="rank",
        kind=StepKind.TOOL,
        ref="agents.research_digest.tools.dedupe_rank:run",
        inputs=["docs_norm"],
        outputs=["docs_ranked"],
        config={"limit": 6},
    )
    artifacts = [_artifact("docs_norm", "ccc")]

    key_a = compute_step_cache_key(step_a, Mode.DEBUG, artifacts)
    key_b = compute_step_cache_key(step_b, Mode.DEBUG, artifacts)

    assert key_a != key_b


def test_compute_step_cache_key_changes_when_input_hash_changes() -> None:
    step = StepSpec(
        id="render",
        kind=StepKind.TOOL,
        ref="agents.research_digest.tools.render:run",
        inputs=["docs_ranked"],
        outputs=["digest_md"],
        config={},
    )
    artifacts_a = [_artifact("docs_ranked", "hash-a")]
    artifacts_b = [_artifact("docs_ranked", "hash-b")]

    key_a = compute_step_cache_key(step, Mode.EVAL, artifacts_a)
    key_b = compute_step_cache_key(step, Mode.EVAL, artifacts_b)

    assert key_a != key_b


def test_compute_step_cache_key_changes_when_mode_changes() -> None:
    step = StepSpec(
        id="render",
        kind=StepKind.TOOL,
        ref="agents.research_digest.tools.render:run",
        inputs=["docs_ranked"],
        outputs=["digest_md"],
        config={},
    )
    artifacts = [_artifact("docs_ranked", "hash-a")]

    key_prod = compute_step_cache_key(step, Mode.PROD, artifacts)
    key_debug = compute_step_cache_key(step, Mode.DEBUG, artifacts)

    assert key_prod != key_debug
