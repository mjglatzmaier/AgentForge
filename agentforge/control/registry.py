"""Agent registry loading and capability indexing."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from agentforge.control.discovery import discover_agent_spec_paths
from agentforge.contracts.models import AgentRuntimeKind, AgentSpec


@dataclass(frozen=True)
class AgentRegistry:
    """Deterministic in-memory registry of discovered agent specs."""

    agents_by_id: dict[str, AgentSpec]
    capability_index: dict[str, tuple[str, ...]]

    def get(self, agent_id: str) -> AgentSpec | None:
        return self.agents_by_id.get(agent_id)

    def list_agent_ids(self) -> list[str]:
        return list(self.agents_by_id.keys())

    def resolve_capability(self, capability: str) -> list[AgentSpec]:
        capability_key = capability.strip()
        if not capability_key:
            return []
        agent_ids = self.capability_index.get(capability_key, ())
        return [self.agents_by_id[agent_id] for agent_id in agent_ids]


def export_registry_snapshot(run_dir: str | Path, registry: AgentRegistry) -> Path:
    """Persist deterministic registry snapshot to runs/<run_id>/control/registry.json."""

    registry_path = Path(run_dir) / "control" / "registry.json"
    payload = build_registry_snapshot(registry)
    _write_json_atomic(registry_path, payload)
    return registry_path


def build_registry_snapshot(registry: AgentRegistry) -> dict[str, Any]:
    """Build deterministic JSON-serializable registry payload."""

    return {
        "schema_version": 1,
        "agents": [
            registry.agents_by_id[agent_id].model_dump(mode="json")
            for agent_id in registry.list_agent_ids()
        ],
        "capability_index": {
            capability: list(agent_ids)
            for capability, agent_ids in sorted(registry.capability_index.items())
        },
    }


def load_agent_registry(
    repo_root: str | Path,
    *,
    env_value: str | None = None,
) -> AgentRegistry:
    """Load registry from standard discovery roots."""

    spec_paths = discover_agent_spec_paths(repo_root, env_value=env_value)
    return load_agent_registry_from_paths(spec_paths)


def load_agent_registry_from_paths(spec_paths: list[str | Path]) -> AgentRegistry:
    """Load registry from explicit `agent.yaml` paths deterministically."""

    records: list[tuple[str, Path, AgentSpec]] = []
    seen_by_id: dict[str, Path] = {}

    for path in sorted(Path(item).resolve() for item in spec_paths):
        payload = _load_agent_yaml(path)
        spec = _parse_agent_spec(path, payload)
        _validate_plugin_metadata(path, spec)
        existing_path = seen_by_id.get(spec.agent_id)
        if existing_path is not None:
            raise ValueError(
                "Duplicate agent_id "
                f"'{spec.agent_id}' found at {existing_path} and {path}"
            )
        seen_by_id[spec.agent_id] = path
        records.append((spec.agent_id, path, spec))

    records.sort(key=lambda item: item[0])
    agents_by_id = {agent_id: spec for agent_id, _path, spec in records}
    capability_index = _build_capability_index(agents_by_id)
    return AgentRegistry(agents_by_id=agents_by_id, capability_index=capability_index)


def _load_agent_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Agent spec file not found: {path}")
    try:
        loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"Failed to parse agent YAML at {path}: {exc}") from exc
    if not isinstance(loaded, dict):
        loaded_type = type(loaded).__name__
        raise ValueError(f"Agent YAML root must be a mapping at {path}; got {loaded_type}")
    return loaded


def _parse_agent_spec(path: Path, payload: dict) -> AgentSpec:
    try:
        return AgentSpec.model_validate(payload)
    except ValidationError as exc:
        raise ValueError(f"Invalid AgentSpec at {path}: {exc}") from exc


def _build_capability_index(agents_by_id: dict[str, AgentSpec]) -> dict[str, tuple[str, ...]]:
    index: dict[str, list[str]] = {}
    for agent_id, spec in agents_by_id.items():
        for capability in spec.intents + spec.tags:
            index.setdefault(capability, []).append(agent_id)

    normalized: dict[str, tuple[str, ...]] = {}
    for capability, agent_ids in index.items():
        normalized[capability] = tuple(sorted(agent_ids))
    return normalized


def _validate_plugin_metadata(path: Path, spec: AgentSpec) -> None:
    if spec.runtime.type is None:
        raise ValueError(
            f"Invalid AgentSpec at {path}: runtime.type is required for plugin runtime metadata."
        )
    if spec.runtime.runtime is AgentRuntimeKind.PYTHON and spec.runtime.entrypoint.count(":") != 1:
        raise ValueError(
            f"Invalid AgentSpec at {path}: python runtime entrypoint must be 'module.path:function'."
        )
    if not spec.capabilities.operations:
        raise ValueError(
            f"Invalid AgentSpec at {path}: capabilities.operations must declare at least one operation."
        )

    seen_ops: set[str] = set()
    duplicates: list[str] = []
    for operation in spec.capabilities.operations:
        name = operation.name
        if name in seen_ops:
            duplicates.append(name)
            continue
        seen_ops.add(name)
    if duplicates:
        duplicate_names = ", ".join(sorted(set(duplicates)))
        raise ValueError(
            f"Invalid AgentSpec at {path}: capabilities.operations contains duplicate name(s): "
            f"{duplicate_names}"
        )


def _write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)
