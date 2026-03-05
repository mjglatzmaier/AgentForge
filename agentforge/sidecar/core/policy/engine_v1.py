"""Policy engine v1 for capability and approval decisioning."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlparse

from agentforge.sidecar.core.policy.config_v1 import AgentIdentityV1, PolicyConfigV1
from agentforge.sidecar.core.policy.decision import PolicyDecisionResult


class PolicyEngineV1:
    """Deterministic policy evaluator for one policy snapshot."""

    def __init__(self, policy: PolicyConfigV1) -> None:
        self._policy = policy
        self._rate_limit_counts: dict[str, int] = {}
        self._rate_limit_seen_request_ids: dict[str, set[str]] = {}

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

    def evaluate_constraints(
        self,
        *,
        agent_id: str,
        operation: str,
        input_payload: Mapping[str, Any],
    ) -> PolicyDecisionResult:
        policy_entry = self._policy.agents.get(agent_id)
        if policy_entry is None:
            return PolicyDecisionResult(
                decision="allow",
                reason_code="CONSTRAINTS_SKIPPED_AGENT_UNKNOWN",
                policy_snapshot_id=self._policy.policy_snapshot_id,
            )
        constraints = policy_entry.constraints.get(operation)
        if constraints is None:
            return PolicyDecisionResult(
                decision="allow",
                reason_code="CONSTRAINTS_NOT_CONFIGURED",
                policy_snapshot_id=self._policy.policy_snapshot_id,
            )

        if constraints.domain_allowlist:
            domain = _extract_domain(input_payload)
            if domain is None:
                return self._deny("CONSTRAINT_DOMAIN_MISSING")
            if domain not in constraints.domain_allowlist:
                return self._deny("CONSTRAINT_DOMAIN_NOT_ALLOWED")

        if constraints.recipient_allowlist:
            recipients = _extract_recipients(input_payload)
            if not recipients:
                return self._deny("CONSTRAINT_RECIPIENT_MISSING")
            if any(item not in constraints.recipient_allowlist for item in recipients):
                return self._deny("CONSTRAINT_RECIPIENT_NOT_ALLOWED")

        if constraints.symbol_allowlist:
            symbol = _extract_symbol(input_payload)
            if symbol is None:
                return self._deny("CONSTRAINT_SYMBOL_MISSING")
            if symbol not in constraints.symbol_allowlist:
                return self._deny("CONSTRAINT_SYMBOL_NOT_ALLOWED")

        if constraints.max_notional_usd is not None:
            notional = _extract_notional(input_payload)
            if notional is None:
                return self._deny("CONSTRAINT_NOTIONAL_INVALID")
            if notional > constraints.max_notional_usd:
                return self._deny("CONSTRAINT_NOTIONAL_EXCEEDED")

        return PolicyDecisionResult(
            decision="allow",
            reason_code="CONSTRAINTS_PASSED",
            policy_snapshot_id=self._policy.policy_snapshot_id,
        )

    def evaluate_rate_limit(
        self,
        *,
        agent_id: str,
        operation: str,
        request_id: str,
    ) -> PolicyDecisionResult:
        policy_entry = self._policy.agents.get(agent_id)
        if policy_entry is None:
            return PolicyDecisionResult(
                decision="allow",
                reason_code="RATE_LIMIT_SKIPPED_AGENT_UNKNOWN",
                policy_snapshot_id=self._policy.policy_snapshot_id,
            )

        limit = policy_entry.rate_limits.get(operation)
        if limit is None:
            return PolicyDecisionResult(
                decision="allow",
                reason_code="RATE_LIMIT_NOT_CONFIGURED",
                policy_snapshot_id=self._policy.policy_snapshot_id,
            )

        key = f"{self._policy.policy_snapshot_id}|{agent_id}|{operation}"
        seen = self._rate_limit_seen_request_ids.setdefault(key, set())
        if request_id in seen:
            return PolicyDecisionResult(
                decision="allow",
                reason_code="RATE_LIMIT_IDEMPOTENT_REQUEST",
                policy_snapshot_id=self._policy.policy_snapshot_id,
            )

        count = self._rate_limit_counts.get(key, 0)
        if count >= limit:
            return self._deny("RATE_LIMIT_EXCEEDED")

        seen.add(request_id)
        self._rate_limit_counts[key] = count + 1
        return PolicyDecisionResult(
            decision="allow",
            reason_code="RATE_LIMIT_ALLOWED",
            policy_snapshot_id=self._policy.policy_snapshot_id,
        )

    def _deny(self, reason_code: str) -> PolicyDecisionResult:
        return PolicyDecisionResult(
            decision="deny",
            reason_code=reason_code,
            policy_snapshot_id=self._policy.policy_snapshot_id,
        )


def _extract_domain(payload: Mapping[str, Any]) -> str | None:
    domain_value = payload.get("domain")
    if isinstance(domain_value, str):
        domain = domain_value.strip().lower()
        if domain:
            return domain
    url_value = payload.get("url")
    if isinstance(url_value, str):
        parsed = urlparse(url_value.strip())
        host = (parsed.hostname or "").strip().lower()
        if host:
            return host
    return None


def _extract_recipients(payload: Mapping[str, Any]) -> list[str]:
    for key in ("to", "recipient", "recipients"):
        value = payload.get(key)
        if isinstance(value, str):
            items = [item.strip().lower() for item in value.split(",")]
            return [item for item in items if item]
        if isinstance(value, list):
            recipients: list[str] = []
            for item in value:
                if isinstance(item, str):
                    normalized = item.strip().lower()
                    if normalized:
                        recipients.append(normalized)
            return recipients
    return []


def _extract_symbol(payload: Mapping[str, Any]) -> str | None:
    symbol_value = payload.get("symbol")
    if isinstance(symbol_value, str):
        symbol = symbol_value.strip().lower()
        if symbol:
            return symbol
    return None


def _extract_notional(payload: Mapping[str, Any]) -> float | None:
    notional_value = payload.get("notional_usd")
    if isinstance(notional_value, bool):
        return None
    if isinstance(notional_value, (int, float)):
        return float(notional_value)
    return None
