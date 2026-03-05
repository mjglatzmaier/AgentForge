# Task Refactor 03: Lumen Workbench API and Visualization Readiness

## Objective

Expose a stable local control API so Lumen can visualize workflows, approvals, and artifacts while preserving strict trust boundaries.

## Scope (In)

- Add read APIs for runs, graph state, events, timeline, and artifacts.
- Add mutation APIs for approvals and run control (`pause/resume/cancel`).
- Enforce authn/authz for operator actions.
- Add cursor-based event streaming and poll fallback.
- Define Dear ImGui-oriented workbench client contract and projections.

## Scope (Out)

- Rich UI implementation inside this repository.
- Remote multi-tenant API hosting.

## Implementation Checklist

1. Define API contracts aligned with `docs/lumen-integration-v1.md`.
2. Implement minimal local `agentd` endpoints (or adapters) with typed responses.
3. Add run graph projection from control plan + runtime state.
4. Add approval endpoints wired to approval gateway.
5. Add artifact index/read endpoint with path sandbox checks.
6. Add Dear ImGui workbench projection contract:
   - run list view model
   - event timeline projection model
   - pending approval modal model
7. Add tests:
   - event pagination and cursor correctness
   - approval action flow
   - run control state transitions
   - artifact path traversal prevention

## Acceptance Criteria

- Lumen can render live run state and pending approvals from local API.
- Operator approval actions are enforced and reflected in event stream.
- Artifact access is read-only and restricted to run sandbox.
- API behavior is cross-platform and does not rely on OS-specific path assumptions.
- Workbench contract supports an optional Dear ImGui native client without API changes.

---

## Implementation Slices (execute one at a time)

### Slice 03-A: Complete Local Read + Run-Control Surface

**Goal:** Finish missing `agentd` API adapters/projections required for Workbench visibility and control flow.

**In scope**
- Add typed adapters for:
  - `GET /runs/{run_id}` (run summary/details)
  - `GET /runs/{run_id}/graph` (control-plan graph + node states)
  - `GET /runs/{run_id}/timeline` (normalized timeline projection from events)
  - `POST /runs/{run_id}:pause|resume|cancel` (local run-control state transitions)
- Keep existing approvals/events/artifacts behavior unchanged.
- Preserve cursor semantics for event listing/streaming.

**Out of scope**
- Authn/authz enforcement logic (covered in Slice 03-B).
- UI implementation.

**Suggested file targets**
- `agentforge/sidecar/agentd/api/runs_api.py`
- `agentforge/sidecar/agentd/api/events_api.py` (timeline adapter if needed)
- `agentforge/sidecar/workbench/lumen_projection_v1.py`
- `agentforge/tests/sidecar/test_workbench_v1.py` (+ new API-focused tests if needed)

**Checklist**
- [X] Add/extend response models for run detail, graph projection, timeline projection, run-control result.
- [X] Implement run-detail and graph readers from run dir (`control/snapshot.json`, plan/state artifacts when present).
- [X] Implement timeline projection adapter from run events (stable ordering by event append order/timestamp).
- [X] Implement pause/resume/cancel adapters with deterministic local state persistence.
- [X] Add tests for:
  - missing-file fallback behavior (`unknown`/empty projections, no crashes),
  - graph/timeline projection correctness,
  - pause/resume/cancel state transitions and idempotency.

**Slice 03-A acceptance**
- Workbench can request run detail/graph/timeline and receive typed, stable responses.
- Local run-control mutations persist state transitions deterministically.
- All new tests pass; no regressions in existing sidecar tests.

### Slice 03-B: Operator Authn/Authz Guardrails for Mutations

**Goal:** Enforce operator session authorization on mutation endpoints without breaking read-only local observability.

**In scope**
- Add a minimal operator auth contract for mutation APIs:
  - approvals: approve/deny
  - run control: pause/resume/cancel
- Enforce authorization checks in API adapter boundary (not in connectors).
- Emit auditable denial reason codes for unauthorized mutation attempts.

**Out of scope**
- External IAM/SSO integration.
- Remote multi-tenant identity management.

**Suggested file targets**
- `agentforge/sidecar/agentd/api/approvals_api.py`
- `agentforge/sidecar/agentd/api/runs_api.py` (run-control mutations)
- `agentforge/sidecar/core/contracts/` (operator auth context model if needed)
- `agentforge/tests/sidecar/test_approvals_v1.py`
- `agentforge/tests/sidecar/test_workbench_v1.py` (or new `test_agentd_authz_v1.py`)

**Checklist**
- [X] Define a typed operator auth context (e.g., operator id + scopes/permissions).
- [X] Add mutation adapter signatures requiring auth context (or explicit auth token envelope).
- [X] Enforce allow/deny checks with stable codes (e.g., `OPERATOR_UNAUTHORIZED`, `OPERATOR_FORBIDDEN`).
- [X] Keep read endpoints (`GET` runs/events/artifacts/approvals) accessible per current local policy unless explicitly restricted.
- [X] Add tests for:
  - unauthorized mutation denied,
  - authorized mutation succeeds,
  - denial paths are auditable and do not mutate state.

**Slice 03-B acceptance**
- Mutation endpoints require valid operator authorization.
- Unauthorized mutation attempts are denied with explicit, stable codes and audit visibility.
- Read-only observability remains functional for Workbench.
