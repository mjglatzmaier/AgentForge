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

1. Inventory Lumen modules (renderer, scheduler, containers, memory, input) and map to AgentForge needs.
2. Extract required view-model/interface ideas into side-car workbench contracts.
3. Define Dear ImGui client spike plan:
   - fetch runs/events/approvals/artifacts from `agentd`
   - render timeline + approval modal + artifact panel
4. Keep submodule temporary; produce a post-harvest remove plan.
5. Add tests for API projection correctness in Python side-car layer.

## Acceptance Criteria

- A documented keep/discard matrix exists for Lumen components.
- AgentForge side-car APIs remain language-agnostic and stable.
- Dear ImGui client path is feasible without kernel refactor.
- Temporary Lumen submodule can be removed with no core regressions.
