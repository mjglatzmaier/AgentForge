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
            "entrypoint": "agents.arxiv_research.entrypoint:run",
            "timeout_s": 120,
            "max_concurrency": 2,
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
