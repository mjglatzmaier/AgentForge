import json
from pathlib import Path

import pytest

from agentforge.control.registry import (
    build_registry_snapshot,
    export_registry_snapshot,
    load_agent_registry,
    load_agent_registry_from_paths,
)


def _write_agent_yaml(
    path: Path,
    *,
    agent_id: str,
    intents: list[str],
    tags: list[str],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        f"""
agent_id: {agent_id}
version: 1.0.0
description: test
intents: {intents}
tags: {tags}
input_contracts: [Req]
output_contracts: [Res]
runtime:
  runtime: python
  entrypoint: agents.{agent_id}.entrypoint:run
  timeout_s: 30
  max_concurrency: 1
operations_policy:
  terminal_access: none
  allowed_commands: []
  fs_scope: [outputs/]
  network_access: none
  network_allowlist: []
""".strip(),
        encoding="utf-8",
    )


def test_load_agent_registry_from_paths_is_deterministic(tmp_path: Path) -> None:
    # Paths are intentionally passed in reverse order.
    first = tmp_path / "b.yaml"
    second = tmp_path / "a.yaml"
    _write_agent_yaml(first, agent_id="agent.beta", intents=["research"], tags=["digest"])
    _write_agent_yaml(second, agent_id="agent.alpha", intents=["research"], tags=["digest"])

    registry = load_agent_registry_from_paths([first, second])

    assert registry.list_agent_ids() == ["agent.alpha", "agent.beta"]
    assert [spec.agent_id for spec in registry.resolve_capability("research")] == [
        "agent.alpha",
        "agent.beta",
    ]
    assert registry.capability_index["digest"] == ("agent.alpha", "agent.beta")


def test_load_agent_registry_rejects_duplicate_agent_id(tmp_path: Path) -> None:
    one = tmp_path / "one" / "agent.yaml"
    two = tmp_path / "two" / "agent.yaml"
    _write_agent_yaml(one, agent_id="agent.dup", intents=["x"], tags=["y"])
    _write_agent_yaml(two, agent_id="agent.dup", intents=["x"], tags=["z"])

    with pytest.raises(ValueError, match="Duplicate agent_id"):
        load_agent_registry_from_paths([one, two])


def test_load_agent_registry_from_repo_uses_discovery_roots(tmp_path: Path) -> None:
    demo = tmp_path / "agents" / "demo" / "agent.yaml"
    pack = tmp_path / "agents_packs" / "pack_a" / "agents" / "x" / "agent.yaml"
    env_dir = tmp_path / "extra_agents"
    env_agent = env_dir / "z" / "agent.yaml"
    _write_agent_yaml(demo, agent_id="agent.demo", intents=["research"], tags=["demo"])
    _write_agent_yaml(pack, agent_id="agent.pack", intents=["research"], tags=["pack"])
    _write_agent_yaml(env_agent, agent_id="agent.env", intents=["research"], tags=["env"])

    registry = load_agent_registry(tmp_path, env_value=str(env_dir))
    assert registry.list_agent_ids() == ["agent.demo", "agent.env", "agent.pack"]


def test_export_registry_snapshot_writes_control_registry_json(tmp_path: Path) -> None:
    agent_yaml = tmp_path / "agents" / "demo" / "agent.yaml"
    _write_agent_yaml(agent_yaml, agent_id="agent.demo", intents=["research"], tags=["demo"])
    registry = load_agent_registry(tmp_path)

    registry_path = export_registry_snapshot(tmp_path / "runs" / "run-001", registry)
    payload = json.loads(registry_path.read_text(encoding="utf-8"))

    assert registry_path == tmp_path / "runs" / "run-001" / "control" / "registry.json"
    assert payload["schema_version"] == 1
    assert payload["agents"][0]["agent_id"] == "agent.demo"


def test_build_registry_snapshot_is_deterministic(tmp_path: Path) -> None:
    first = tmp_path / "b.yaml"
    second = tmp_path / "a.yaml"
    _write_agent_yaml(first, agent_id="agent.beta", intents=["research"], tags=["digest"])
    _write_agent_yaml(second, agent_id="agent.alpha", intents=["research"], tags=["digest"])

    registry_a = load_agent_registry_from_paths([first, second])
    registry_b = load_agent_registry_from_paths([second, first])
    assert build_registry_snapshot(registry_a) == build_registry_snapshot(registry_b)


def test_arxiv_research_agentspec_validates_under_registry() -> None:
    repo_root = Path(__file__).resolve().parents[3]
    agent_yaml = repo_root / "agents" / "arxiv_research" / "agent.yaml"

    registry = load_agent_registry_from_paths([agent_yaml])
    spec = registry.get("arxiv.research")

    assert spec is not None
    assert spec.version == "1.0.0"
    assert spec.runtime.type is not None
    assert spec.runtime.type.value == "python_subprocess"
    assert spec.runtime.entrypoint == "agents.arxiv_research.entrypoint:run"
    assert spec.runtime.max_concurrency == 2
    assert [operation.name for operation in spec.capabilities.operations] == [
        "fetch_and_snapshot",
        "synthesize_digest",
        "render_report",
    ]
    assert spec.operations_policy.network_allowlist == ["export.arxiv.org"]
