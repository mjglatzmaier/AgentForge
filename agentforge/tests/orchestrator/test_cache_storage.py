import json
from pathlib import Path

from agentforge.contracts.models import ArtifactRef
from agentforge.orchestrator.cache import load_cache_record, save_cache_record


def _artifact(name: str, sha: str) -> ArtifactRef:
    return ArtifactRef(
        name=name,
        type="json",
        path=f"runs/run-001/steps/00_fetch/outputs/{name}.json",
        sha256=sha,
        producer_step_id="fetch",
    )


def test_cache_record_round_trip(tmp_path: Path) -> None:
    artifacts = [_artifact("docs", "aaa"), _artifact("summary", "bbb")]

    cache_file = save_cache_record(
        base_dir=tmp_path,
        pipeline_name="research_digest",
        cache_key="cache-key-1",
        outputs=artifacts,
    )
    loaded = load_cache_record(tmp_path, "research_digest", "cache-key-1")
    raw = json.loads(cache_file.read_text(encoding="utf-8"))

    assert cache_file == tmp_path / "runs" / ".cache" / "research_digest" / "cache-key-1.json"
    assert raw["pipeline_name"] == "research_digest"
    assert loaded == artifacts


def test_cache_miss_returns_none(tmp_path: Path) -> None:
    loaded = load_cache_record(tmp_path, "research_digest", "missing")
    assert loaded is None
