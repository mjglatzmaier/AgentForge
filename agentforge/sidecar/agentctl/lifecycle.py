"""Cross-platform service lifecycle helpers for agentctl up/down."""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Mapping


_LOCALHOST_BIND_VALUES = {"127.0.0.1", "localhost", "::1"}
_KNOWN_CONNECTORS = ("gmaild", "exchanged", "rssd")


@dataclass(frozen=True)
class ServiceSpec:
    name: str
    host: str
    port: int
    command: list[str]


@dataclass(frozen=True)
class RuntimeConfig:
    bind_host: str
    agentd_port: int
    gmaild_port: int
    exchanged_port: int
    rssd_port: int
    enabled_connectors: tuple[str, ...]
    state_dir: Path


def load_runtime_config(env: Mapping[str, str] | None = None) -> RuntimeConfig:
    values = dict(env or os.environ)
    bind_host = values.get("AGENTFORGE_BIND_HOST", "127.0.0.1").strip()
    if bind_host not in _LOCALHOST_BIND_VALUES:
        raise ValueError("AGENTFORGE_BIND_HOST must be localhost-only by default.")
    enabled_connectors = _parse_connectors(values.get("AGENTFORGE_ENABLED_CONNECTORS", ""))
    state_dir = Path(values.get("AGENTFORGE_STATE_DIR", ".agentforge/sidecar")).resolve()
    return RuntimeConfig(
        bind_host=bind_host,
        agentd_port=_parse_port(values, "AGENTFORGE_AGENTD_PORT", 8410),
        gmaild_port=_parse_port(values, "AGENTFORGE_GMAILD_PORT", 8411),
        exchanged_port=_parse_port(values, "AGENTFORGE_EXCHANGED_PORT", 8412),
        rssd_port=_parse_port(values, "AGENTFORGE_RSSD_PORT", 8413),
        enabled_connectors=enabled_connectors,
        state_dir=state_dir,
    )


def build_service_specs(
    config: RuntimeConfig,
    env: Mapping[str, str] | None = None,
) -> dict[str, ServiceSpec]:
    values = dict(env or os.environ)
    specs: dict[str, ServiceSpec] = {
        "agentd": ServiceSpec(
            name="agentd",
            host=config.bind_host,
            port=config.agentd_port,
            command=_command_from_env(
                values=values,
                env_key="AGENTFORGE_AGENTD_CMD",
                default=_default_service_command(config.bind_host, config.agentd_port),
            ),
        )
    }

    connector_ports = {
        "gmaild": config.gmaild_port,
        "exchanged": config.exchanged_port,
        "rssd": config.rssd_port,
    }
    for connector in config.enabled_connectors:
        specs[connector] = ServiceSpec(
            name=connector,
            host=config.bind_host,
            port=connector_ports[connector],
            command=_command_from_env(
                values=values,
                env_key=f"AGENTFORGE_{connector.upper()}_CMD",
                default=_default_service_command(config.bind_host, connector_ports[connector]),
            ),
        )
    return specs


def up(
    *,
    env: Mapping[str, str] | None = None,
    spawn: Callable[[list[str]], int] | None = None,
) -> dict[str, int]:
    config = load_runtime_config(env)
    specs = build_service_specs(config, env)
    spawn_fn = spawn or _spawn_process
    started: dict[str, int] = {}
    for name, spec in specs.items():
        started[name] = spawn_fn(spec.command)
    _write_state(config.state_dir / "services.json", specs=specs, pids=started)
    return started


def down(
    *,
    env: Mapping[str, str] | None = None,
    terminate: Callable[[int], None] | None = None,
) -> list[int]:
    config = load_runtime_config(env)
    state_path = config.state_dir / "services.json"
    if not state_path.exists():
        return []
    payload = json.loads(state_path.read_text(encoding="utf-8"))
    services_raw = payload.get("services", {})
    if not isinstance(services_raw, dict):
        raise ValueError("Invalid services state: expected object at services.")
    terminate_fn = terminate or _terminate_pid
    terminated: list[int] = []
    for item in services_raw.values():
        if not isinstance(item, dict):
            continue
        pid = item.get("pid")
        if not isinstance(pid, int):
            continue
        terminate_fn(pid)
        terminated.append(pid)
    state_path.unlink(missing_ok=True)
    return terminated


def _write_state(path: Path, *, specs: Mapping[str, ServiceSpec], pids: Mapping[str, int]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 1,
        "services": {
            name: {
                "pid": pids[name],
                "host": spec.host,
                "port": spec.port,
                "command": list(spec.command),
            }
            for name, spec in sorted(specs.items())
        },
    }
    temp_path = path.with_suffix(f"{path.suffix}.tmp")
    temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(path)


def _command_from_env(*, values: Mapping[str, str], env_key: str, default: list[str]) -> list[str]:
    raw = values.get(env_key, "").strip()
    if not raw:
        return default
    parts = shlex.split(raw)
    if not parts:
        raise ValueError(f"{env_key} cannot be empty when set.")
    return parts


def _default_service_command(host: str, port: int) -> list[str]:
    return [sys.executable, "-m", "http.server", str(port), "--bind", host]


def _spawn_process(command: list[str]) -> int:
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL,
    )
    return int(process.pid)


def _terminate_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return
    os.kill(pid, signal.SIGTERM)


def _parse_port(values: Mapping[str, str], key: str, default: int) -> int:
    raw = values.get(key, str(default)).strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer.") from exc
    if value < 1 or value > 65535:
        raise ValueError(f"{key} must be between 1 and 65535.")
    return value


def _parse_connectors(raw: str) -> tuple[str, ...]:
    if not raw.strip():
        return ()
    parsed = [item.strip().lower() for item in raw.split(",") if item.strip()]
    unknown = sorted(set(parsed) - set(_KNOWN_CONNECTORS))
    if unknown:
        raise ValueError(f"Unknown connector(s) in AGENTFORGE_ENABLED_CONNECTORS: {unknown}")
    ordered = [name for name in _KNOWN_CONNECTORS if name in parsed]
    return tuple(ordered)

