# AgentForge Refactor Tasks v2 (Control Plane + Extensible Multi-Agent Runtime)

## Feasibility

This refactor is feasible and aligns with the current strengths of AgentForge: typed contracts, manifest-indexed artifacts, deterministic run folders, and reusable YAML pipelines.
The safest path is incremental: keep the existing orchestrator and pipeline runtime as the foundation, then add a control plane and agent dispatch in layers.

## Architectural Direction

### Core principle
- Keep the orchestrator deterministic and contract-first.
- Add a **Control Plane** as an explicit component that plans, schedules, and governs multi-agent execution.

### Proposed runtime split
- **Control Plane**: planning, routing, dependency graph, policy checks, lifecycle (pause/resume/restart), observability.
- **Execution Plane**: launches agent runs through runtime adapters (`python`, `npm`, later `container`), persists artifacts and step state.

### Use existing tools first
- Reuse current AgentForge runner, manifest storage, and step/pipeline contracts.
- Reuse existing YAML pipeline system for internal tool chains per agent.
- Add LangGraph as an **optional adapter** only after native execution plan support is stable and tested.

---

## Definition of Done (applies to every task below)

- Unit tests added/updated for the changed behavior.
- `source .venv/bin/activate && python -m pytest` passes (or fails only due to pre-existing unrelated failures, documented in PR notes).
- Code is simple, typed, and professionally named (clear class/function/variable names).
- Comments are concise and only used where logic is non-obvious.
- No hidden side effects or implicit coupling across agents.

---

## Phase 0 — Baseline and ADR Setup (Implementation Order Anchor)

- [ ] 0.1 Add architecture decision records (ADR) for:
  - Control Plane responsibilities
  - Runtime adapter model (`python`/`npm`/`container`)
  - Native plan engine first, LangGraph adapter second
- [ ] 0.2 Capture baseline tests and representative run artifacts for regression comparison.

Acceptance criteria:
- ADRs are approved and referenced by implementation tasks.
- Baseline behavior is reproducible for later parity checks.

---

## Phase 1 — Control Plane Contracts (Explicit and Minimal)

- [ ] 1.1 Add `ControlPlan` model:
  - `plan_id`, `nodes`, `edges`, `max_parallel`, `policy_snapshot`
- [ ] 1.2 Add `ControlNode` model:
  - `node_id`, `agent_id`, `inputs`, `outputs`, `depends_on`, `state`, `retry_policy`
- [ ] 1.3 Add lifecycle state model:
  - `pending | ready | running | paused | succeeded | failed | cancelled`
- [ ] 1.4 Persist control-plane state under run artifacts (`runs/<run_id>/control/`).

Acceptance criteria:
- Control-plane schemas validate deterministically.
- State can be serialized/deserialized with no information loss.
- Unit tests cover state transitions and invalid graph definitions.

---

## Phase 2 — Agent Package Spec v1 (Extensibility Surface)

- [ ] 2.1 Define `AgentSpec` in `agent.yaml`:
  - identity: `agent_id`, `version`, `description`
  - capability metadata: intents/tags
  - interfaces: `input_contracts`, `output_contracts`
  - runtime metadata: `runtime`, `command`, `cwd`, `timeout_s`, `max_concurrency`
- [ ] 2.2 Define explicit `operations_policy`:
  - `terminal_access` (`none` | `restricted`)
  - `allowed_commands`, `blocked_commands`
  - `fs_scope`
  - `network_access` + allowlist
- [ ] 2.3 Add strict loader/validator for all agent specs at startup.
- [ ] 2.4 Enforce unique `agent_id` and schema validation errors with clear messages.

Acceptance criteria:
- Adding an agent requires only `agents/<name>/agent.yaml` + entrypoint + contracts.
- Policy violations are rejected before launch.
- Unit tests cover valid/invalid specs and policy schema edge cases.

---

## Phase 3 — Prompt System + Output Contract Cleanliness

- [ ] 3.1 Standardize `agent_prompt.md` structure:
  - `System`
  - `Scope`
  - `Constraints`
  - `Output Rules`
- [ ] 3.2 Implement prompt compiler:
  - combines `agent.yaml` metadata + `agent_prompt.md` + runtime context
  - emits deterministic prompt artifact in debug mode
- [ ] 3.3 Keep output contracts machine-enforced:
  - Pydantic models as source of truth
  - optional exported JSON schemas for tooling
- [ ] 3.4 Ensure prompt text can evolve without orchestrator code changes.

Acceptance criteria:
- Prompt edits are isolated to prompt files unless behavior contracts change.
- Contract validation remains strict and independent of prompt wording.
- Unit tests verify deterministic prompt compilation and contract enforcement.

---

## Phase 4 — Registry and Dispatch Preparation

- [ ] 4.1 Build `AgentRegistry` from validated specs.
- [ ] 4.2 Implement capability index and deterministic candidate ranking.
- [ ] 4.3 Add direct-dispatch (`agent_id`) and capability-dispatch paths.
- [ ] 4.4 Export registry snapshot into run metadata for traceability.

Acceptance criteria:
- Registry loads all agents deterministically.
- Candidate resolution is reproducible for same input/context.
- Unit tests verify tie-breaking and resolution behavior.

---

## Phase 5 — Control Plane Scheduler (Dependencies + Parallelism)

- [ ] 5.1 Implement dependency-aware scheduler:
  - node runs only when dependencies succeeded and inputs are present
- [ ] 5.2 Implement bounded parallelism:
  - global `max_parallel`
  - per-agent `max_concurrency`
- [ ] 5.3 Implement artifact handoff:
  - downstream reads upstream outputs only via manifest refs
- [ ] 5.4 Implement failure semantics:
  - explicit node failure states
  - transient retry policy only where declared

Acceptance criteria:
- Agent A -> Agent B dependencies are explicit and enforced.
- Parallel execution never violates declared limits.
- Unit tests cover dependency blocking/unblocking and collision-free artifact handoff.

---

## Phase 6 — Pause / Resume / Restart Lifecycle

- [ ] 6.1 Add pause command semantics:
  - stop scheduling new nodes
  - mark running nodes as interrupt-requested
- [ ] 6.2 Add resume semantics from persisted control-plane state.
- [ ] 6.3 Add targeted restart semantics:
  - restart selected failed/cancelled nodes
  - validate downstream invalidation and artifact freshness
- [ ] 6.4 Record lifecycle events in run artifacts for debugging/audit.

Acceptance criteria:
- Lifecycle operations work across process restarts (not memory-only).
- Resume/restart behavior is deterministic from persisted state.
- Unit tests cover pause/resume/restart and partial-run recovery.

---

## Phase 7 — Runtime Adapters and OS Strategy

- [ ] 7.1 Implement runtime adapters:
  - `PythonRuntimeAdapter`
  - `NpmRuntimeAdapter`
  - `ContainerRuntimeAdapter` (stub/optional)
- [ ] 7.2 Enforce operations policy in adapter layer (not prompt-only).
- [ ] 7.3 Keep metadata OS-agnostic; define V1 support as Unix/macOS.
- [ ] 7.4 Add optional per-OS command overrides for future Windows support.

Acceptance criteria:
- Agent runtime selection is config-driven and pluggable.
- Terminal-enabled agents can only run policy-allowed operations.
- Unit tests verify adapter selection and policy enforcement outcomes.

---

## Phase 8 — Dispatch LLM + Optional LangGraph Adapter

- [ ] 8.1 Add dispatch planner with strict structured output schema.
- [ ] 8.2 Validate planner output before creating control plan.
- [ ] 8.3 Add deterministic fallback routing when planner output is invalid.
- [ ] 8.4 Add optional LangGraph adapter behind a feature flag:
  - same contracts
  - same artifact model
  - no required dependency for core path

Acceptance criteria:
- Planner decisions are inspectable and reproducible in debug artifacts.
- Core execution works without LangGraph.
- Unit tests verify planner validation and fallback routing.

---

## Phase 9 — Research Digest Migration and CLI Chat Integration

- [ ] 9.1 Convert research digest into `agent.yaml` + entrypoint package.
- [ ] 9.2 Reuse existing internal YAML pipeline for digest tool chain.
- [ ] 9.3 Add orchestrator dispatch integration for interactive CLI/chat mode.
- [ ] 9.4 Add parallel multi-agent demo scenario with explicit dependencies.

Acceptance criteria:
- Research digest outputs preserve existing contracts and run-folder quality.
- CLI path can dispatch one or multiple agents in a single request.
- Integration tests verify parity against baseline digest behavior.

---

## Phase 10 — Hardening, Evaluation, and Release Gate

- [ ] 10.1 Add regression suite:
  - routing quality
  - dependency scheduling
  - lifecycle controls
  - operations-policy enforcement
- [ ] 10.2 Add load/concurrency tests for multi-agent runs.
- [ ] 10.3 Add release checklist and migration notes for adding new agents.

Acceptance criteria:
- Refactor meets stability and determinism thresholds.
- New-agent onboarding is documented and requires no orchestrator code changes.
- Test suite and quality gates are green for release.
