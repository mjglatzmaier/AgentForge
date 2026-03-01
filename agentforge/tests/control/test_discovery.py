from pathlib import Path

from agentforge.control.discovery import discover_agent_spec_paths


def _write_agent_yaml(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("agent_id: test\nversion: 1.0.0\n", encoding="utf-8")


def test_discovery_scans_default_roots(tmp_path: Path) -> None:
    repo_root = tmp_path
    demo_agent = repo_root / "agents" / "demo" / "agent.yaml"
    private_agent = repo_root / "agents_packs" / "pack_a" / "agents" / "x" / "agent.yaml"
    _write_agent_yaml(demo_agent)
    _write_agent_yaml(private_agent)

    discovered = discover_agent_spec_paths(repo_root, env_value="")

    assert discovered == sorted([demo_agent.resolve(), private_agent.resolve()], key=str)


def test_discovery_includes_env_roots_with_relative_and_absolute_paths(tmp_path: Path) -> None:
    repo_root = tmp_path
    rel_agent = repo_root / "custom_rel" / "a" / "agent.yaml"
    abs_root = repo_root / "custom_abs"
    abs_agent = abs_root / "b" / "agent.yaml"
    _write_agent_yaml(rel_agent)
    _write_agent_yaml(abs_agent)

    env_value = f"custom_rel,{abs_root}"
    discovered = discover_agent_spec_paths(repo_root, env_value=env_value)

    assert rel_agent.resolve() in discovered
    assert abs_agent.resolve() in discovered


def test_discovery_deduplicates_and_is_stable(tmp_path: Path) -> None:
    repo_root = tmp_path
    agent_yaml = repo_root / "agents" / "demo" / "agent.yaml"
    _write_agent_yaml(agent_yaml)

    discovered = discover_agent_spec_paths(repo_root, env_value="agents,agents")

    assert discovered == [agent_yaml.resolve()]
