"""Policy engine v1 for capability and approval decisioning."""

from __future__ import annotations

from agentforge.sidecar.core.policy.config_v1 import AgentIdentityV1, PolicyConfigV1
from agentforge.sidecar.core.policy.decision import PolicyDecisionResult


class PolicyEngineV1:
    """Deterministic policy evaluator for one policy snapshot."""

    def __init__(self, policy: PolicyConfigV1) -> None:
        self._policy = policy

    @property
    def snapshot_id(self) -> str:
        return self._policy.policy_snapshot_id

    def identity_for(self, agent_id: str) -> AgentIdentityV1 | None:
        policy_entry = self._policy.agents.get(agent_id)
        if policy_entry is None:
            return None
        return AgentIdentityV1(
            agent_id=agent_id,
            role=policy_entry.role,
            allowed_capabilities=list(policy_entry.allowed_capabilities),
        )

    def evaluate(
        self,
        *,
        agent_id: str,
        capability: str,
        operation: str,
    ) -> PolicyDecisionResult:
        policy_entry = self._policy.agents.get(agent_id)
        if policy_entry is None:
            if self._policy.defaults.deny_by_default:
                return PolicyDecisionResult(
                    decision="deny",
                    reason_code="AGENT_NOT_ALLOWED",
                    policy_snapshot_id=self._policy.policy_snapshot_id,
                )
            return PolicyDecisionResult(
                decision="allow",
                reason_code="DEFAULT_ALLOW",
                policy_snapshot_id=self._policy.policy_snapshot_id,
            )

        if capability not in policy_entry.allowed_capabilities:
            return PolicyDecisionResult(
                decision="deny",
                reason_code="CAPABILITY_DENIED",
                policy_snapshot_id=self._policy.policy_snapshot_id,
            )

        if operation in policy_entry.approval_required_ops:
            return PolicyDecisionResult(
                decision="require_approval",
                reason_code="APPROVAL_REQUIRED",
                policy_snapshot_id=self._policy.policy_snapshot_id,
            )

        return PolicyDecisionResult(
            decision="allow",
            reason_code="CAPABILITY_ALLOWED",
            policy_snapshot_id=self._policy.policy_snapshot_id,
        )

