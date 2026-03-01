import pytest
from pydantic import ValidationError

from agentforge.contracts.models import AgentSpec


def _agent_spec_payload() -> dict:
    return {
        "agent_id": "arxiv.research",
        "version": "1.0.0",
        "description": "Research digest agent",
        "intents": ["research", "digest"],
        "tags": ["arxiv"],
        "input_contracts": ["ResearchRequest"],
        "output_contracts": ["ResearchDigest"],
        "runtime": {
            "runtime": "python",
            "type": "python_subprocess",
            "entrypoint": "agents.arxiv_research.entrypoint:run",
            "timeout_s": 120,
            "max_concurrency": 2,
        },
        "capabilities": {
            "operations": [
                {
                    "name": "fetch_and_snapshot",
                    "inputs": ["request_json"],
                    "outputs": ["raw_feed_snapshot", "papers_raw"],
                }
            ]
        },
        "operations_policy": {
            "terminal_access": "none",
            "allowed_commands": [],
            "fs_scope": ["outputs/"],
            "network_access": "allowlist",
            "network_allowlist": ["export.arxiv.org"],
        },
    }


def test_agent_spec_valid_payload() -> None:
    spec = AgentSpec.model_validate(_agent_spec_payload())
    assert spec.agent_id == "arxiv.research"
    assert spec.runtime.runtime.value == "python"
    assert spec.runtime.type.value == "python_subprocess"
    assert spec.capabilities.operations[0].name == "fetch_and_snapshot"
    assert spec.capabilities.operations[0].outputs == ["raw_feed_snapshot", "papers_raw"]


def test_agent_spec_validation_errors_are_clear() -> None:
    payload = _agent_spec_payload()
    payload["runtime"]["max_concurrency"] = 0

    with pytest.raises(ValidationError, match="max_concurrency must be >= 1"):
        AgentSpec.model_validate(payload)


def test_agent_spec_requires_network_allowlist_for_allowlist_mode() -> None:
    payload = _agent_spec_payload()
    payload["operations_policy"]["network_allowlist"] = []

    with pytest.raises(ValidationError, match="network_allowlist is required"):
        AgentSpec.model_validate(payload)


def test_agent_spec_rejects_empty_list_entries() -> None:
    payload = _agent_spec_payload()
    payload["tags"] = ["  "]

    with pytest.raises(ValidationError, match="list entries must be non-empty"):
        AgentSpec.model_validate(payload)


def test_agent_spec_serialization_is_stable() -> None:
    payload = _agent_spec_payload()
    spec_a = AgentSpec.model_validate(payload)
    spec_b = AgentSpec.model_validate(payload)
    assert spec_a.model_dump(mode="json") == spec_b.model_dump(mode="json")
    assert spec_a.model_dump_json() == spec_b.model_dump_json()


def test_agent_spec_infers_runtime_type_when_missing() -> None:
    payload = _agent_spec_payload()
    payload["runtime"].pop("type")
    spec = AgentSpec.model_validate(payload)
    assert spec.runtime.type is not None
    assert spec.runtime.type.value == "python_subprocess"


def test_agent_spec_requires_python_entrypoint_module_function_format() -> None:
    payload = _agent_spec_payload()
    payload["runtime"]["entrypoint"] = "agents.arxiv_research.entrypoint"
    with pytest.raises(ValidationError, match="module.path:function"):
        AgentSpec.model_validate(payload)


def test_agent_spec_accepts_container_runtime_contract_surface() -> None:
    payload = _agent_spec_payload()
    payload["runtime"] = {
        "runtime": "container",
        "type": "container",
        "entrypoint": "unused.container.entrypoint",
        "container": {
            "image": "ghcr.io/example/arxiv-agent:1.0.0",
            "command": ["python", "-m", "agent_entrypoint"],
            "env": {"PYTHONUNBUFFERED": "1"},
            "io_contract": "json-stdio",
        },
        "timeout_s": 120,
        "max_concurrency": 2,
    }
    spec = AgentSpec.model_validate(payload)
    assert spec.runtime.runtime.value == "container"
    assert spec.runtime.container is not None
    assert spec.runtime.container.image == "ghcr.io/example/arxiv-agent:1.0.0"
    assert spec.runtime.container.command == ["python", "-m", "agent_entrypoint"]
    assert spec.runtime.container.env == {"PYTHONUNBUFFERED": "1"}
    assert spec.runtime.container.io_contract.value == "json-stdio"


def test_agent_spec_requires_container_contract_when_runtime_is_container() -> None:
    payload = _agent_spec_payload()
    payload["runtime"] = {
        "runtime": "container",
        "type": "container",
        "entrypoint": "unused.container.entrypoint",
        "timeout_s": 120,
        "max_concurrency": 2,
    }
    with pytest.raises(ValidationError, match="requires runtime.container"):
        AgentSpec.model_validate(payload)
