"""Agent spec discovery helpers."""

from __future__ import annotations

import os
from pathlib import Path

AGENT_PACKS_DIRS_ENV = "AGENTFORGE_AGENT_PACKS_DIRS"


def discover_agent_spec_paths(
    repo_root: str | Path,
    *,
    env_value: str | None = None,
) -> list[Path]:
    """Discover `agent.yaml` files from default and configured roots."""

    root = Path(repo_root)
    search_roots = _default_discovery_roots(root)
    search_roots.extend(_env_discovery_roots(root, env_value=env_value))

    discovered: dict[str, Path] = {}
    for search_root in search_roots:
        if not search_root.exists() or not search_root.is_dir():
            continue
        for path in search_root.rglob("agent.yaml"):
            if not path.is_file():
                continue
            resolved = path.resolve()
            discovered[str(resolved)] = resolved

    return [discovered[key] for key in sorted(discovered.keys())]


def _default_discovery_roots(root: Path) -> list[Path]:
    roots: list[Path] = [root / "agents"]
    agent_packs_dir = root / "agents_packs"
    if agent_packs_dir.exists() and agent_packs_dir.is_dir():
        for pack_dir in sorted(agent_packs_dir.iterdir()):
            if pack_dir.is_dir():
                roots.append(pack_dir / "agents")
    return roots


def _env_discovery_roots(root: Path, *, env_value: str | None) -> list[Path]:
    raw = env_value if env_value is not None else os.getenv(AGENT_PACKS_DIRS_ENV, "")
    roots: list[Path] = []
    for entry in raw.split(","):
        normalized = entry.strip()
        if not normalized:
            continue
        path = Path(normalized)
        if not path.is_absolute():
            path = root / path
        roots.append(path)
    return roots
