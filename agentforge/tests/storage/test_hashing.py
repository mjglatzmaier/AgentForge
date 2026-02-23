from datetime import datetime, timezone
from pathlib import Path

from agentforge.contracts.models import Mode, RunConfig
from agentforge.storage.hashing import sha256_file, sha256_json, sha256_str, stable_json_dumps


def test_sha256_json_is_stable_for_permuted_dict_keys() -> None:
    first = {"b": 2, "a": 1, "nested": {"y": 2, "x": 1}}
    second = {"nested": {"x": 1, "y": 2}, "a": 1, "b": 2}

    assert stable_json_dumps(first) == stable_json_dumps(second)
    assert sha256_json(first) == sha256_json(second)


def test_sha256_file_matches_known_hash(tmp_path: Path) -> None:
    file_path = tmp_path / "sample.txt"
    file_path.write_text("hello world", encoding="utf-8")

    assert sha256_file(file_path) == sha256_str("hello world")
    assert sha256_file(file_path) == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"


def test_sha256_json_is_consistent_for_pydantic_models() -> None:
    run_config = RunConfig(
        run_id="run-001",
        timestamp=datetime(2026, 2, 23, 0, 0, tzinfo=timezone.utc),
        mode=Mode.DEBUG,
        pipeline_name="research_digest",
        git_sha="abc123",
    )

    assert sha256_json(run_config) == sha256_json(run_config.model_dump(mode="json"))
