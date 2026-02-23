"""Deterministic hashing helpers used for artifact and cache identity."""

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel


def sha256_file(path: str | Path) -> str:
    """Hash file bytes using SHA-256."""

    digest = hashlib.sha256()
    file_path = Path(path)
    with file_path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8192), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_str(value: str) -> str:
    """Hash a UTF-8 string using SHA-256."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def stable_json_dumps(obj: Any) -> str:
    """Serialize JSON deterministically with sorted keys and compact separators."""

    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_json(obj: Any) -> str:
    """Hash a JSON-serializable object or Pydantic model deterministically."""

    serializable = obj.model_dump(mode="json") if isinstance(obj, BaseModel) else obj
    return sha256_str(stable_json_dumps(serializable))
