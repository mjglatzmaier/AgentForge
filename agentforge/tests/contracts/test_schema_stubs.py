import json
from pathlib import Path


def test_schema_stubs_exist_and_are_json_objects() -> None:
    root = Path(__file__).resolve().parents[3]
    schema_dir = root / "schemas"
    schema_files = [
        "doc.json",
        "digest.json",
        "manifest.json",
        "pipeline.json",
        "agent.json",
    ]

    for schema_file in schema_files:
        file_path = schema_dir / schema_file
        assert file_path.exists()
        loaded = json.loads(file_path.read_text(encoding="utf-8"))
        assert isinstance(loaded, dict)
