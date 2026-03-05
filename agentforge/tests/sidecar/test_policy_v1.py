from __future__ import annotations

from pathlib import Path

from agentforge.sidecar.core.policy import PolicyConfigV1, PolicyEngineV1, load_policy_config


def test_load_policy_config_from_yaml(tmp_path: Path) -> None:
    policy_path = tmp_path / "policy.yaml"
    policy_path.write_text(
        "\n".join(
            [
                "policy_version: 1",
                "policy_snapshot_id: pol_test_1",
                "defaults:",
                "  deny_by_default: true",
                "agents:",
                "  market.scanner:",
                "    role: trader",
                "    allowed_capabilities: [exchange.read]",
                "    approval_required_ops: [exchange.place_order]",
            ]
        ),
        encoding="utf-8",
    )

    loaded = load_policy_config(policy_path)
    assert loaded.policy_snapshot_id == "pol_test_1"
    assert loaded.agents["market.scanner"].role == "trader"


def test_policy_engine_decisions_change_by_snapshot() -> None:
    strict = PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_strict",
            "defaults": {"deny_by_default": True},
            "agents": {
                "market.scanner": {
                    "role": "trader",
                    "allowed_capabilities": ["exchange.read"],
                    "approval_required_ops": ["exchange.place_order"],
                }
            },
        }
    )
    relaxed = PolicyConfigV1.model_validate(
        {
            "policy_version": 1,
            "policy_snapshot_id": "pol_relaxed",
            "defaults": {"deny_by_default": True},
            "agents": {
                "market.scanner": {
                    "role": "trader",
                    "allowed_capabilities": ["exchange.read", "exchange.place_order"],
                    "approval_required_ops": [],
                }
            },
        }
    )

    strict_engine = PolicyEngineV1(strict)
    relaxed_engine = PolicyEngineV1(relaxed)

    strict_result = strict_engine.evaluate(
        agent_id="market.scanner",
        capability="exchange.place_order",
        operation="exchange.place_order",
    )
    relaxed_result = relaxed_engine.evaluate(
        agent_id="market.scanner",
        capability="exchange.place_order",
        operation="exchange.place_order",
    )

    assert strict_result.decision == "deny"
    assert relaxed_result.decision == "allow"

