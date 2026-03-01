# AgentForge Refactor Tasks (Dispatch-Orchestrated Multi-Agent Platform)

## Feasibility

Yes, this refactor is feasible with the current codebase as a base.
The strongest enablers already exist: typed output contracts, manifest-indexed artifacts, deterministic run folders, and reusable YAML pipelines.
The main complexity is not data modeling; it is safe parallel execution, routing quality, and clear agent boundaries.

## Refactor Goals

- Convert “research digest pipeline” into a standalone agent package callable by an orchestrator.
- Evolve orchestrator into a dispatch layer that can choose and launch one or more agents.
- Make onboarding new agents low-friction and contract-driven.
- Preserve current strengths: manifests, run folder traceability, and internal tool pipelines.
- Support concurrent multi-agent execution with deterministic artifacts and observability.

## Non-Goals (for initial refactor)

- No hard dependency on LangGraph unless native execution proves insufficient.
- No replacement of artifact contracts or run storage model.
- No hidden implicit communication between agents (all cross-agent exchange remains artifact-based).

## Additional Feasibility Assessment

### A) NPM-based agent execution model

Feasible, with one architectural adjustment: make execution runtime pluggable instead of npm-only.

Recommended direction:
- Keep orchestrator runtime-agnostic via launch adapters (`python`, `npm`, optional `container`).
- Let each agent declare runtime in `agent.yaml` and provide launch command + working directory.
- Use npm primarily for Node/TS agents; keep Python agents on existing execution path.

Example `agent.yaml` execution block:
```yaml
execution:
  runtime: "npm" # python | npm | container
  command: ["npm", "run", "agent:start", "--"]
  cwd: "agents/research_digest"
  timeout_s: 180
  max_concurrency: 2
  env_allowlist: ["OPENAI_API_KEY", "ANTHROPIC_API_KEY"]
```

Cleanliness/extensibility notes:
- This supports mixed-language agents and isolated dependencies per agent.
- Avoid hardcoding install logic in orchestrator; agent runtime should fail explicitly if deps are missing.
- Require lockfiles (`package-lock.json`, `poetry.lock`, etc.) for reproducible runs.

### B) Prompt + output-contract architecture

Also feasible, and high-leverage for long-term maintainability.

Recommended split:
- `agent.yaml`: machine-readable metadata (capabilities, IO contracts, runtime, version).
- `agent_prompt.md`: human-editable system prompt and behavior rules.
- `contracts/*.json` (or Pydantic source + exported schema): strict output contracts.

For “all metadata in markdown”:
- Possible via markdown front matter, but not ideal as primary source for execution-critical fields.
- Best compromise: keep canonical metadata in `agent.yaml`; allow optional markdown front matter for prompt-scoped fields only.

### C) Execution controls, boundaries, and dependency model

Feasible and strongly recommended for V1 to avoid hidden coupling between agents.

Required behavior:
- Agent execution should use orchestrator-managed tools/runtimes only (no implicit shell access).
- Parallelization should be plan-driven and bounded by global + per-agent limits.
- Cross-agent dependencies must be explicit in execution plan edges (`agent_b` waits on artifacts from `agent_a`).
- Pause/restart/resume should be run-state based (manifest + step status), not in-memory only.

Minimal control-plane model:
- `ExecutionNode`: `node_id`, `agent_id`, `inputs`, `outputs`, `depends_on`, `state`.
- `state`: `pending | running | paused | succeeded | failed | cancelled`.
- Restart policy: restart only `failed`/`cancelled` nodes unless `force_rerun` is set.
- Resume policy: continue from persisted `pending`/`paused` nodes with artifact revalidation.

Terminal-command agent policy:
- Agents that need terminal access must declare an explicit operations policy in `agent.yaml`.
- Policy should define allowlisted commands, blocked commands, filesystem scope, and network policy.
- System prompt may restate policy, but enforcement must be outside prompt text (runtime-level).

OS portability:
- V1 target: Unix/macOS shell behavior for determinism.
- Keep metadata OS-agnostic (`runtime`, `command`, `cwd`, `env`) and add optional per-OS command overrides later.

---

## Phase 1 — Agent Packaging Contract

- [ ] 1.1 Define `AgentSpec` schema (e.g., `schemas/agent.json` + Pydantic model) with:
  - `agent_id`, `version`, `description`
  - `capabilities` (tags/intents)
  - `entrypoint` (callable ref)
  - `input_contracts` / `output_contracts`
  - `execution` hints (`supports_parallel`, `max_concurrency`, `timeouts`)
- [ ] 1.2 Add per-agent config file in each `agents/<agent_name>/` directory (e.g., `agent.yaml`).
- [ ] 1.3 Build loader/validator for agent specs at startup.
- [ ] 1.4 Add tests for invalid/missing fields and duplicate `agent_id`s.
- [ ] 1.5 Add runtime launcher schema:
  - `runtime` (`python` | `npm` | `container`)
  - `command`, `cwd`, `timeout_s`, `env_allowlist`
  - `max_concurrency` (agent-local bound)
- [ ] 1.6 Add `agent_prompt.md` convention and loader:
  - stable section headers (`System`, `Scope`, `Constraints`, `Output Rules`)
  - optional prompt-local front matter
  - deterministic prompt materialization in debug artifacts
- [ ] 1.7 Add `operations_policy` schema in `agent.yaml`:
  - `terminal_access` (`none` | `restricted`)
  - `allowed_commands` (explicit allowlist)
  - `blocked_commands` (always denied)
  - `fs_scope` (workspace-relative paths)
  - `network_access` (`none` | `allowlist`)
  - `network_allowlist` (domains/hosts)

Acceptance criteria:
- Agents are discoverable from filesystem config alone.
- Agent metadata can be used without importing agent runtime code.
- Prompt text can be revised without orchestrator code edits.
- Agent operation boundaries are machine-validated before launch.

---

## Phase 2 — Agent Registry + Capability Index

- [ ] 2.1 Implement `AgentRegistry` in core orchestrator package.
- [ ] 2.2 Index agents by `agent_id` and capabilities.
- [ ] 2.3 Support static dispatch (direct by `agent_id`) and capability-based lookup.
- [ ] 2.4 Add deterministic conflict resolution when multiple agents match.

Acceptance criteria:
- Orchestrator can resolve candidate agents for a task deterministically.
- Registry supports easy extension by adding a new `agents/<name>/agent.yaml`.

---

## Phase 3 — Dispatch LLM Planning Layer

- [ ] 3.1 Define structured planner output schema:
  - selected agent(s)
  - reason
  - parallel groups
  - required inputs
  - expected outputs
- [ ] 3.2 Build dispatch system prompt template containing:
  - orchestrator role/constraints
  - available agents and versions
  - agent metadata + capability summaries
  - safety and determinism rules
- [ ] 3.3 Add planner fallback mode (rules-only routing) if LLM planner fails validation.
- [ ] 3.4 Log planner decisions into run metadata for debugging and eval.

Acceptance criteria:
- Planner output is schema-validated before execution.
- Routing decisions are inspectable in run artifacts.

---

## Phase 4 — Concurrent Multi-Agent Execution Engine

- [ ] 4.1 Introduce explicit execution plan model (`ExecutionPlan`, `ExecutionNode`, dependencies).
- [ ] 4.2 Implement bounded parallel execution (`max_parallel_agents`) with cancellation + timeout handling.
- [ ] 4.3 Ensure each agent gets isolated step/run subdirectories and artifact namespaces.
- [ ] 4.4 Merge outputs via manifest rules (no artifact name collisions; explicit aliases required).
- [ ] 4.5 Add retry policy only for transient failures and keep failures explicit in step status.
- [ ] 4.6 Add dependency-aware scheduling:
  - node executes only when `depends_on` artifacts are present + valid
  - downstream nodes read upstream artifacts through manifest references only
- [ ] 4.7 Add pause/resume/restart controls:
  - pause pending scheduling and mark running nodes as interrupt requested
  - resume from persisted run state
  - restart targeted nodes with dependency invalidation checks

Acceptance criteria:
- Multiple agents can run simultaneously in one orchestrated run.
- Artifacts remain deterministic, conflict-free, and debuggable.
- Dependency ordering is explicit and reproducible across runs.
- Pause/resume/restart behavior is consistent from persisted run metadata.

---

## Phase 5 — Research Digest Migration

- [ ] 5.1 Create `agents/research_digest/agent.yaml` with capability and version metadata.
- [ ] 5.2 Wrap existing digest pipeline as agent entrypoint (reuse current YAML pipeline/tool chain).
- [ ] 5.3 Keep current output contracts (`digest_json`, `digest_md`, citation report) unchanged.
- [ ] 5.4 Add migration tests to guarantee parity with current behavior.

Acceptance criteria:
- Research digest runs as an agent via orchestrator dispatch with no contract regressions.

---

## Phase 6 — CLI Chat/Session Mode

- [ ] 6.1 Add chat/session command path that invokes dispatcher planner each turn.
- [ ] 6.2 Persist session context as artifacts/metadata, not global mutable state.
- [ ] 6.3 Allow planner to launch parallel agents when request decomposes into independent tasks.
- [ ] 6.4 Provide transparent “plan + launched agents + outputs” trace in debug mode.

Acceptance criteria:
- CLI chat can autonomously select and run one or multiple agents per turn.

---

## Phase 7 — Evaluation and Regression Harness

- [ ] 7.1 Add routing-quality eval set (intent -> expected agent(s)).
- [ ] 7.2 Add concurrency stress tests (artifact collisions, timeout races, partial failures).
- [ ] 7.3 Add deterministic replay tests from stored planner output artifacts.
- [ ] 7.4 Add baseline-vs-refactor comparison for research digest outputs.
- [ ] 7.5 Add execution-controls tests:
  - dependency blocking/unblocking
  - paused run resume semantics
  - restart behavior with partial artifact reuse
- [ ] 7.6 Add operation-policy enforcement tests for terminal-enabled agents.

Acceptance criteria:
- Refactor has measurable routing quality and stability metrics.
- Regression risk is controlled before default enablement.

---

## Phase 8 — OS Portability Strategy

- [ ] 8.1 Define V1 support matrix: Unix/macOS first, Windows deferred.
- [ ] 8.2 Add launcher abstraction that avoids shell-specific syntax in core planner.
- [ ] 8.3 Add optional per-OS command overrides in `agent.yaml`:
  - `execution.commands.unix`
  - `execution.commands.macos`
  - `execution.commands.windows` (future)
- [ ] 8.4 Add CI checks ensuring unsupported OS targets fail with clear errors.

Acceptance criteria:
- Core architecture remains OS-agnostic in metadata and contracts.
- V1 execution is reliable on Unix/macOS with explicit non-support messaging elsewhere.

---

## Extensibility Rules (Must-Haves)

- New agent onboarding must require:
  1. `agent.yaml`
  2. entrypoint callable
  3. declared input/output contracts
  4. tests
- No orchestrator code changes for normal new-agent addition.
- Agent-to-agent communication occurs only through declared artifacts.
- Planner must consume registry metadata, never hardcoded agent lists.

---

## LangGraph Decision

Recommended approach:
- Start with native AgentForge execution plan + bounded parallel runtime.
- Add an optional LangGraph adapter only if advanced graph-state features become necessary.

Rationale:
- Current architecture already aligns with deterministic artifact contracts and run-folder debugging.
- Native-first minimizes framework lock-in while keeping future integration possible.
