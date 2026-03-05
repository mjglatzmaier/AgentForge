# Task Refactor 02: Policy/Approval Gate + Connector Isolation

## Objective

Enforce security-first execution by making policy decisions and approvals mandatory at kernel dispatch boundaries, and by isolating secrets inside connectors.

## Scope (In)

- Implement policy evaluator with deterministic decision outputs.
- Add approval token workflow for irreversible operations.
- Introduce connector registration and per-operation schema validation.
- Add secret redaction and audit decision logging.

## Scope (Out)

- Enterprise IAM integration (future work).
- Managed cloud secret stores as hard requirement.

## Implementation Checklist

- [X] Add typed policy decision model (`allow`, `deny`, `require_approval` + reason code).
- [X] Implement policy loader/validator for v1 YAML schema.
- [X] Build approval store with TTL + single-use token semantics.
- [X] Enforce operation constraints (domain allowlist, symbol/notional caps, recipient caps).
- [X] Standardize connector error translation to bounded taxonomy.
- [X] Add audits for all decisions and approval actions.
- [X] Add tests:
  - deny-by-default behavior
  - approval-required branch
  - constraint enforcement
  - secret redaction in logs/events

## Acceptance Criteria

- Unauthorized operations are denied with explicit reason code.
- Approval-required operations cannot execute without valid approval token.
- Connector calls do not expose secrets in kernel logs/events.
- Policy outcomes are reproducible from policy snapshot + request input.

## Follow-on Breakdown (recommended)

Use these smaller tasks to reduce implementation friction and isolate risk:

- `tasks/task-refactor-05.md` — approval token TTL + single-use hardening (**completed**).
- `tasks/task-refactor-06.md` — operation constraints + rate-limit enforcement (**completed**).
- `tasks/task-refactor-07.md` — audit logging, secret redaction, bounded error taxonomy (**completed**).
