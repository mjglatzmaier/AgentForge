# Task Refactor 04: Lumen Harvest and Dear ImGui Client Path

## Objective

Harvest useful components from temporary Lumen submodule and define a clean, optional native workbench client path without coupling AgentForge core to game-engine code.

## Scope (In)

- Evaluate Lumen components for reuse in workbench UX.
- Keep only reusable concepts/contracts, not engine runtime dependencies.
- Define optional Dear ImGui client architecture against `agentd` APIs.
- Document keep/discard decisions and migration steps.

## Scope (Out)

- Embedding full game-engine renderer into AgentForge kernel.
- Rewriting side-car kernel/core in C.

## Harvest Criteria

Keep candidates only if they are:
1. Directly useful for run/event/approval/artifact UX.
2. Independent from Vulkan/game-loop assumptions.
3. Low-friction to maintain with current team and toolchain.

Discard if they:
1. Require heavy engine/runtime coupling.
2. Duplicate simpler Python-side implementations.
3. Add cross-platform build complexity without clear payoff.

## Implementation Checklist

- [X] Inventory Lumen modules (renderer, scheduler, containers, memory, input) and map to AgentForge needs.
- [X] Extract required view-model/interface ideas into side-car workbench contracts.
- [X] Define Dear ImGui client spike plan:
  - fetch runs/events/approvals/artifacts from `agentd`
  - render timeline + approval modal + artifact panel
- [X] Keep submodule temporary; produce a post-harvest remove plan.
- [X] Add tests for API projection correctness in Python side-car layer.

## Harvest Matrix (v1, completed)

| Lumen area | Decision | AgentForge target | Rationale |
| --- | --- | --- | --- |
| Timeline visualization patterns | Keep (concept) | `agentforge/sidecar/workbench/lumen_projection_v1.py` + `GET /runs/{run_id}/timeline` | Direct UX value for run/event observability with no renderer coupling. |
| Approval interaction patterns | Keep (concept) | `agentforge/sidecar/agentd/api/approvals_api.py` + workbench approval modal projection | Maps cleanly to policy-gated approve/deny flow. |
| Artifact browsing patterns | Keep (concept) | `agentforge/sidecar/agentd/api/artifacts_api.py` + artifact viewer projection | Useful and language-agnostic with sandbox-safe file access. |
| Scheduling visuals concepts | Keep (concept) | run graph/detail/timeline APIs (`runs_api.py`, `events_api.py`) | Reused as data-contract ideas only; no engine loop adoption. |
| Renderer/Vulkan/GLFW runtime | Discard | N/A | Heavy engine/runtime coupling; violates low-friction cross-platform scope. |
| Engine containers/memory allocators | Discard | N/A | Not needed for Python-first sidecar and duplicates simpler runtime assumptions. |
| Input/game-loop subsystem | Discard | N/A | Dear ImGui client can handle input independently of kernel/control plane. |

## Dear ImGui Client Spike Plan (implementation-ready)

1. Build a thin native client that only calls local `agentd` APIs:
   - `GET /runs`, `GET /runs/{run_id}`, `GET /runs/{run_id}/graph`
   - `GET /runs/{run_id}/timeline`, `GET /approvals`, `GET /runs/{run_id}/artifacts`
   - mutation calls: approvals + run control
2. Implement three first-class panels:
   - Runs/Graph panel
   - Timeline panel (cursor polling with optional stream)
   - Approval modal + artifact viewer panel
3. Keep all policy/approval/security enforcement in `agentd`; client remains presentation-only.

## Post-Harvest Remove Plan (completed)

1. Harvest concepts/contracts into sidecar APIs and workbench projections.
2. Verify no runtime dependency on submodule remains in source tree.
3. Remove temporary Lumen submodule and keep API contracts stable.
4. Validate regression safety with sidecar/workbench test coverage.

## Verification Notes

- Projection/API correctness covered by sidecar tests, including:
  - `agentforge/tests/sidecar/test_workbench_v1.py`
  - `agentforge/tests/sidecar/test_runs_api_v1.py`

## Acceptance Criteria

- A documented keep/discard matrix exists for Lumen components.
- AgentForge side-car APIs remain language-agnostic and stable.
- Dear ImGui client path is feasible without kernel refactor.
- Temporary Lumen submodule can be removed with no core regressions.
