# Task Refactor 03: Lumen Workbench API and Visualization Readiness

## Objective

Expose a stable local control API so Lumen can visualize workflows, approvals, and artifacts while preserving strict trust boundaries.

## Scope (In)

- Add read APIs for runs, graph state, events, timeline, and artifacts.
- Add mutation APIs for approvals and run control (`pause/resume/cancel`).
- Enforce authn/authz for operator actions.
- Add cursor-based event streaming and poll fallback.

## Scope (Out)

- Rich UI implementation inside this repository.
- Remote multi-tenant API hosting.

## Implementation Checklist

1. Define API contracts aligned with `docs/lumen-integration-v1.md`.
2. Implement minimal local `agentd` endpoints (or adapters) with typed responses.
3. Add run graph projection from control plan + runtime state.
4. Add approval endpoints wired to approval gateway.
5. Add artifact index/read endpoint with path sandbox checks.
6. Add tests:
   - event pagination and cursor correctness
   - approval action flow
   - run control state transitions
   - artifact path traversal prevention

## Acceptance Criteria

- Lumen can render live run state and pending approvals from local API.
- Operator approval actions are enforced and reflected in event stream.
- Artifact access is read-only and restricted to run sandbox.
- API behavior is cross-platform and does not rely on OS-specific path assumptions.
