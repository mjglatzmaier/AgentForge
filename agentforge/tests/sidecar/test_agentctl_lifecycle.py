from __future__ import annotations

import json
from pathlib import Path

import pytest

from agentforge.sidecar.agentctl.lifecycle import down, load_runtime_config, up


def test_load_runtime_config_defaults_localhost() -> None:
    config = load_runtime_config(env={})
    assert config.bind_host == "127.0.0.1"
    assert config.agentd_port == 8410
    assert config.enabled_connectors == ()


def test_load_runtime_config_rejects_non_localhost() -> None:
    with pytest.raises(ValueError):
        load_runtime_config(env={"AGENTFORGE_BIND_HOST": "0.0.0.0"})


def test_up_starts_agentd_and_enabled_connectors(tmp_path: Path) -> None:
    commands: list[list[str]] = []
    next_pid = 1000

    def fake_spawn(command: list[str]) -> int:
        nonlocal next_pid
        commands.append(command)
        next_pid += 1
        return next_pid

    env = {
        "AGENTFORGE_STATE_DIR": str(tmp_path / "state"),
        "AGENTFORGE_ENABLED_CONNECTORS": "gmaild,exchanged",
    }
    started = up(env=env, spawn=fake_spawn)

    assert set(started) == {"agentd", "gmaild", "exchanged"}
    state_path = tmp_path / "state" / "services.json"
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    assert payload["services"]["agentd"]["host"] == "127.0.0.1"
    assert len(commands) == 3


def test_down_stops_started_services(tmp_path: Path) -> None:
    env = {
        "AGENTFORGE_STATE_DIR": str(tmp_path / "state"),
        "AGENTFORGE_ENABLED_CONNECTORS": "gmaild",
    }

    pid = 2000

    def fake_spawn(_command: list[str]) -> int:
        nonlocal pid
        pid += 1
        return pid

    started = up(env=env, spawn=fake_spawn)
    terminated: list[int] = []
    down(env=env, terminate=lambda value: terminated.append(value))

    assert sorted(terminated) == sorted(started.values())
    assert not (tmp_path / "state" / "services.json").exists()

