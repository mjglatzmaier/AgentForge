import pytest
from pydantic import ValidationError

from agentforge.contracts.models import ControlNode, ControlNodeState


def test_control_node_valid_minimal_payload() -> None:
    node = ControlNode(
        node_id="fetch_docs",
        agent_id="agent.research",
        operation="pipeline",
    )

    assert node.state is ControlNodeState.PENDING
    assert node.inputs == []
    assert node.outputs == []


def test_control_node_accepts_explicit_state() -> None:
    node = ControlNode(
        node_id="synthesize",
        agent_id="agent.research",
        operation="callable",
        state=ControlNodeState.READY,
    )
    assert node.state is ControlNodeState.READY


def test_control_node_rejects_invalid_state() -> None:
    with pytest.raises(ValidationError):
        ControlNode(
            node_id="x",
            agent_id="agent.research",
            operation="pipeline",
            state="done",
        )


@pytest.mark.parametrize(
    "field_name",
    ["node_id", "agent_id", "operation"],
)
def test_control_node_rejects_empty_required_strings(field_name: str) -> None:
    payload = {"node_id": "a", "agent_id": "agent.research", "operation": "pipeline"}
    payload[field_name] = "  "
    with pytest.raises(ValidationError, match="must be non-empty"):
        ControlNode(**payload)


def test_control_node_rejects_empty_list_entries() -> None:
    with pytest.raises(ValidationError, match="list entries must be non-empty"):
        ControlNode(
            node_id="a",
            agent_id="agent.research",
            operation="pipeline",
            inputs=["", "doc_1"],
        )


def test_control_node_rejects_non_positive_timeout() -> None:
    with pytest.raises(ValidationError, match="timeout_s must be > 0"):
        ControlNode(
            node_id="a",
            agent_id="agent.research",
            operation="pipeline",
            timeout_s=0,
        )
