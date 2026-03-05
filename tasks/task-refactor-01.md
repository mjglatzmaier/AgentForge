# Task Refactor 01: Side-Car Kernel and Broker Foundation

## Objective

Create a low-risk side-car architecture that introduces Agent OS primitives without breaking existing orchestrator behavior.

## Scope (In)

- Define kernel service boundary and interfaces.
- Introduce broker contract for command/event flow.
- Add compatibility adapter that can execute existing control/orchestrator paths.
- Persist typed event stream and deterministic correlation IDs.

## Scope (Out)

- Full replacement of legacy orchestrator.
- Distributed multi-node scheduling.
- External message bus hard dependency.

## Implementation Checklist

1. Define v1 kernel interfaces:
   - `PolicyEngine`
   - `ApprovalGateway`
   - `BrokerClient`
   - `ConnectorInvoker`
2. Implement in-process broker adapter first (reference implementation).
3. Introduce request/response envelopes aligned with `docs/tool-contract-v1.md`.
4. Add run-level event stream normalization (`events.jsonl` + projections).
5. Build compatibility bridge from current node execution to new invoker path.
6. Add test coverage:
   - deterministic dispatch ordering
   - correlation ID propagation
   - idempotency behavior for write ops
   - error mapping to bounded taxonomy

## Acceptance Criteria

- Existing baseline workflows continue to pass unchanged.
- Kernel can dispatch at least one connector op through broker contract.
- All dispatched ops produce typed lifecycle events.
- Policy deny and approval-required paths are enforced before invocation.
