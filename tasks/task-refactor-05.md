# Task Refactor 05: Approval Token Hardening (TTL + Single-Use)

## Objective

Complete the remaining approval-security gap by introducing explicit approval token semantics with expiry and single-use enforcement.

## Scope (In)

- Add approval token model bound to request context (`run_id`, `request_id`, `operation`, `agent_id`).
- Enforce token TTL (UTC-based expiration).
- Enforce single-use token consumption on successful gated execution.
- Return explicit denial reasons for expired/reused/invalid tokens.

## Scope (Out)

- Multi-party approvals.
- External IAM or SSO-backed approvals.

## Implementation Checklist

- [X] Add typed `ApprovalToken` model (`token_id`, `expires_at_utc`, `used_at_utc`, context fields).
- [X] Extend approval store/gateway to mint token on approve and persist token state.
- [X] Validate token in broker before executing `approval_required` operations.
- [X] Mark token as used atomically once operation is accepted for execution.
- [X] Emit audit events for token issued/expired/used/rejected.
- [X] Add tests:
  - token accepted before expiry,
  - token rejected after TTL,
  - token rejected when reused,
  - token rejected on context mismatch.

## Acceptance Criteria

- Approval-required operations execute only with a valid, unexpired, unused token.
- Reused or expired tokens are denied deterministically with explicit reason codes.
- Token lifecycle is recorded in audit/event logs.
