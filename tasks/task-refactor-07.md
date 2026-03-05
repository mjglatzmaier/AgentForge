# Task Refactor 07: Audit Logging, Secret Redaction, Error Taxonomy

## Objective

Close the final security/operability gaps with centralized audit trails, guaranteed redaction, and bounded connector error mapping.

## Scope (In)

- Add structured audit logger for policy and approval decisions.
- Add reusable redaction utility for sensitive fields before logs/events.
- Map connector and upstream exceptions to bounded error taxonomy.

## Scope (Out)

- SIEM export pipelines.
- Full forensic analytics or long-term retention tooling.

## Implementation Checklist

- [X] Add `AuditEvent` model with actor/run/request/decision/reason/timestamp fields.
- [X] Add append-only audit store (JSONL) under sidecar runtime state.
- [X] Add redaction helper with default sensitive-key patterns (`token`, `secret`, `api_key`, `authorization`).
- [X] Integrate redaction into broker event payloads and approval/policy audit writes.
- [X] Add connector error mapper (`INVALID_REQUEST`, `POLICY_DENIED`, `APPROVAL_REQUIRED`, `CONNECTOR_TIMEOUT`, `UPSTREAM_ERROR`, etc.).
- [X] Add tests:
  - audit events written for allow/deny/approval transitions,
  - sensitive fields redacted in persisted events,
  - exception mapping produces bounded error codes.

## Acceptance Criteria

- All policy/approval decisions produce structured audit records.
- Sensitive values are never persisted in plaintext in sidecar logs/events.
- Connector failures are translated into bounded, predictable error codes.
