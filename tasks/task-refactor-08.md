# Task Refactor 08: Crosscut Pilot Process (End-to-End Sidecar Validation)

## Objective

Run one controlled crosscut process through the sidecar stack (policy -> approval -> broker -> connector -> artifacts -> events/audit -> workbench projections) to validate production-shape behavior before broader rollout.

## Scope (In)

- Define one canonical pilot flow with deterministic inputs and expected outputs.
- Execute the flow through sidecar contracts and adapters, including at least one approval-gated operation.
- Verify event/audit coverage, redaction, and error-code stability through the full path.
- Verify run/workbench projections for runs, graph, timeline, approvals, and artifacts.
- Verify replayability and deterministic control outcomes for identical inputs and policy snapshot.

## Scope (Out)

- Async runtime/event-bus redesign.
- Multi-tenant or remote deployment.
- Throughput/performance optimization beyond basic sanity checks.
- New connector families beyond currently implemented sidecar services.

## Pilot Flow (v1 candidate)

Use a single “analyze + gated action” flow:
1. Read-only ingest/analysis operation(s) produce artifacts.
2. One irreversible action path is policy-gated (`require_approval`).
3. Operator decision (approve/deny) is applied.
4. Downstream behavior and artifacts reflect that decision deterministically.

## Implementation Checklist

1. Define pilot fixture inputs and expected artifacts/event sequence in tests.
2. Add/extend sidecar integration test(s) that run the full control-plane path:
   - policy decisioning
   - broker dispatch
   - approval request/decision
   - connector invocation or denial path
3. Assert full lifecycle observability:
   - run events present and ordered
   - audit events emitted for allow/deny/approval actions
   - sensitive fields redacted in persisted logs/events
4. Assert workbench-readiness from API/projection layer:
   - `GET /runs`, run detail, graph, timeline
   - approvals list and mutation effects
   - artifacts index and safe path behavior
5. Add deterministic replay assertion:
   - same input + policy snapshot -> same node states and equivalent artifact names/paths
6. Document pilot runbook + pass/fail gates in this task (or linked docs section).

## Pass/Fail Gates

- **Pass**:
  - end-to-end test path succeeds in both approval-deny and approval-allow branches,
  - event/audit records are complete and redacted,
  - workbench projections render required run surfaces from produced state,
  - replay assertion passes for deterministic outputs.
- **Fail**:
  - missing/unstable reason codes,
  - irreversible action path bypasses approval gate,
  - secrets appear in persisted event/audit payloads,
  - nondeterministic control outcomes for identical inputs.

## Acceptance Criteria

- One crosscut pilot process is executable via sidecar contracts with deterministic outcomes.
- Approval, policy, broker, connector, artifact, and projection layers are validated together.
- The repository has clear automated tests and a runbook to repeat pilot verification.
