# Task Refactor 06: Policy Constraints + Rate-Limit Enforcement

## Objective

Finish policy enforcement by applying operation-level constraints and rate limits at dispatch time.

## Scope (In)

- Enforce per-operation constraints from policy (domain allowlists, recipient restrictions, symbol/notional guards).
- Enforce policy rate limits (per-agent/per-operation) in the kernel dispatch boundary.
- Standardize deny reason codes for all constraint/rate-limit failures.

## Scope (Out)

- Distributed/global rate limits across multiple hosts.
- Advanced quota billing or tenant-level policies.

## Implementation Checklist

1. Extend policy config schema with normalized `constraints` map per operation.
2. Implement constraint evaluator in policy engine (deterministic pure checks).
3. Add rate-limit state tracking (local snapshot/store) with deterministic keying.
4. Wire policy evaluator results into broker denial path before connector invocation.
5. Add tests:
   - domain/recipient/symbol constraint denials,
   - notional threshold denials,
   - rate-limit exceed denials,
   - allowed path still executes successfully.

## Acceptance Criteria

- Requests violating constraints or limits are denied before connector invocation.
- Denials include explicit, stable reason codes.
- Policy behavior remains reproducible for same input + snapshot.
