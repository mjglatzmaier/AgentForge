## AgentForge Refactor Plan (Backbone Platform + Private Agent Packs)

## Purpose (Crisp Definition)

AgentForge is a **public, deterministic orchestration backbone** for reproducible automation workflows that may involve one or many agents.

It supports:
- Scheduled jobs (cron-like triggers)
- Event-triggered batch runs (webhook/manual; streaming later)
- CLI-driven on-demand requests
- Multi-agent workflows (collect → normalize/enrich → synthesize → report)
- Artifact-indexed traceability (manifest + run folders)
- Lifecycle controls (pause/resume/restart)
- Extensible execution adapters (Python, command/Node, container later)
- Optional data plane adapters (object store, vector store) without coupling core logic

It is NOT:
- A prompt-only agent framework
- A real-time streaming engine (v1 treats streaming as scheduled/event-triggered batches)
- A security sandbox (policy guardrails only; isolation comes with container runtime)

Core invariants:
1) **Message = Artifact**: all inter-component communication occurs via manifest-indexed artifacts.
2) **Deterministic runs**: same inputs + same code produce identical artifacts (modulo timestamps/logging).
3) **Public core / private agents**: platform is public; agent packs are private and integrated via submodules.

---

## Repo Strategy (Public Core + Private Agent Packs)

Public repo (this repo):
- `agentforge/` orchestration backbone
- `eval/` evaluation utilities (optional)
- `schemas/` exported schemas (optional)
- `examples/` example pipelines + demo agents (non-sensitive)

Private repos (agent packs):
- integrated via git submodules under `agents_packs/<pack_name>/`
- each pack contains:
  - `agents/<agent_id>/agent.yaml`
  - prompts/tools/entrypoints/tests (optional internal pipelines)

Design requirement:
- core must not depend on any particular agent pack
- packs load via config + filesystem discovery
- core tests must pass with zero private packs present
- The *ONLY* public agent is the current arxiv research agent - to be kept in this repo as an example agent.
---

## V1 Cutline

V1 includes Phases **0–5** only.
Phases **6–9** are post-V1 extensions.

---

## Cross-cutting Specs to Tighten Before Implementation

### A) Determinism boundaries (external/event data)
- Define which steps are allowed to be non-deterministic (ingest).
- Require ingest steps to write a **snapshot artifact** containing raw responses.
- For replay/eval mode, support using snapshot artifacts instead of re-fetching.
- LLM synthesis determinism policy:
  - **Replay mode** is the deterministic guarantee for synthesis (must be reproducible from fixed inputs/snapshots).
  - **Live mode** is best-effort deterministic only (pin model + prompt template + seed where supported, but no strict byte-for-byte guarantee).
  - Evaluation/regression gates must run in replay mode.

### B) Control event schema + versioning + replay rules
- Define `ControlEvent` schema with:
  - `schema_version`
  - `event_id` (monotonic or uuid)
  - `timestamp_utc`
  - `event_type`
  - `node_id` (optional)
  - `payload` (typed per event_type or freeform dict)
- Replay rules:
  - events are append-only
  - state is derived from events (optionally accelerated by snapshots)
  - schema_version changes require migration strategy (or versioned readers)

### C) operations_policy enforcement semantics + OS matrix
- Define what is enforced at adapter level (best-effort guardrails):
  - allowed command checks
  - cwd/fs_scope allowlist checks
  - network allowlist checks (best effort; real isolation in containers)
- OS support matrix:
  - V1: Unix/macOS
  - Windows: future (explicitly out of scope for V1)
- Define how paths are normalized and validated (POSIX style in artifacts; adapter translates if needed later).

---

## Phases (V1 scope: 0–5)

### Phase 0 — ADRs + Baseline + Repo Boundaries
- ADRs:
  - purpose/non-goals
  - control/execution plane split
  - event log + replay
  - agent packs/submodules
  - determinism boundaries for external data
  - operations_policy semantics + OS matrix
- baseline run artifacts for parity
- `agents_packs/README.md`
- discovery config: `AGENTFORGE_AGENT_PACKS_DIRS`, default `agents/`

### Phase 1 — Control Plane v0 (Batch DAG + Event Log)
- ControlPlan + ControlNode + TriggerSpec
- append-only events.jsonl
- persisted control snapshots (optional)
- deterministic serialization + validation

### Phase 2 — AgentSpec v1 + Discovery
- AgentSpec schema
- pack discovery under `agents/`, `agents_packs/*/agents/`, env dirs
- registry snapshot exported to run control metadata

### Phase 3 — Execution Plane Boundary + Runtime Adapters
- ExecutionRequest/ExecutionResult contracts
- PythonRuntimeAdapter + CommandRuntimeAdapter
- ContainerRuntimeAdapter stub (optional)
- adapter-level policy enforcement

### Phase 4 — Scheduler v1 (Deps + Parallelism + Artifact Handoff)
- dependency-aware scheduling
- bounded parallelism
- manifest-only artifact handoff
- deterministic tie-breaking

### Phase 5 — CLI + Job Trigger Support (Batch-Oriented)
- CLI: run/dispatch/resume/status
- scheduling strategy (OS cron calls CLI, optionally lightweight poller)
- trigger metadata persisted

---

## Post-V1 Extensions (Phases 6–9)
- Multi-agent planning (manual plans + optional LLM planner)
- Reporting + Delivery adapters
- Home security examples (batch/event-triggered collectors)
- Migration + portfolio demos + integration tests

---

## Invariants (Non-Negotiable)
1) Message = Artifact
2) Control-plane state persisted + reconstructable
3) Deterministic scheduler tie-break rules
4) Public core does not depend on private agents
5) Policy enforcement is guardrail-level until containers


## AgentForge V1 Task List (Strict Cutline: Phases 0–5)
Goal:
Ship a public, deterministic orchestration backbone that supports scheduled/event-triggered batch runs, CLI requests, private agent pack discovery, and multi-node execution with auditable control-plane state.

V1 explicitly excludes:
- real-time streaming runtime
- web UI
- delivery/email adapters
- LLM-based dispatch planning
- container isolation (adapter stub allowed)

---

## Definition of Done (Applies to all tasks)

- Unit tests added/updated.
- `python -m pytest` passes.
- Typed, minimal code; no hidden global state.
- Core runs and tests pass with **no private agent packs present**.
- All control-plane state persists under `runs/<run_id>/control/`.
- All inter-component communication via manifest-indexed artifacts.

---

## Phase 0 — ADRs + Baseline + Repo Boundaries

- [ ] 0.1 Add ADRs:
  - purpose/non-goals (batch-first; streaming later)
  - Control Plane / Execution Plane boundary
  - determinism boundaries for external/event data (snapshot artifacts + replay rules)
  - control event schema + versioning + replay rules
  - public core + private agent packs via submodules
  - operations_policy semantics (guardrails) + OS support matrix (Unix/macOS)
- [ ] 0.2 Capture baseline run artifacts for parity regression.
- [ ] 0.3 Add `agents_packs/README.md` describing submodules and expected layout.
- [ ] 0.4 Add discovery config:
  - env var `AGENTFORGE_AGENT_PACKS_DIRS` (comma-separated)
  - default discovery: `agents/` (demo agents only)

Acceptance criteria:
- ADRs define V1 boundaries unambiguously.
- Core passes tests without any private packs.

---

## Phase 1 — Control Plane v0 (Batch DAG + Event Log)

- [X] 1.1 Implement `TriggerSpec`:
  - `kind: manual|schedule|event`
  - `schedule: cron|None`
  - `event_type: str|None`
  - `source: str|None`
  - `request_artifact: str|None`
  - `metadata: dict`
- [X] 1.2 Implement `ControlPlan` (DAG v0):
  - `plan_id`
  - `nodes: list[ControlNode]`
  - `max_parallel`
  - `policy_snapshot`
  - `trigger: TriggerSpec`
  - dependencies via `depends_on` only; cycles rejected
- [X] 1.3 Implement `ControlNode`:
  - `node_id`, `agent_id`, `operation`, `inputs`, `outputs`, `depends_on`
  - `state` enum (pending/ready/running/succeeded/failed/paused/cancelled)
  - `retry_policy`, `timeout_s`, `metadata`
- [X] 1.4 Implement control event log:
  - `runs/<run_id>/control/events.jsonl` append-only
  - `ControlEvent` schema with `schema_version` + replay rules
- [X] 1.5 Persist control-plane artifacts:
  - `plan.json`
  - `trigger.json`
  - `registry.json` (from Phase 2)
  - optional `snapshot.json` (accelerate reload)

Acceptance criteria:
- Control-plan state is durable and reconstructable.
- Event log is versioned and replayable.

---

## Phase 2 — AgentSpec v1 + Agent Pack Discovery

- [X] 2.1 Define `AgentSpec` schema (`agent.yaml`):
  - identity: `agent_id`, `version`, `description`
  - capability metadata: `intents`, `tags`
  - interfaces: `input_contracts`, `output_contracts`
  - runtime: `runtime`, `entrypoint`, `cwd`, `timeout_s`, `max_concurrency`
  - operations_policy: `terminal_access`, `allowed_commands`, `fs_scope`,
    `network_access`, `network_allowlist`
- [X] 2.2 Implement discovery:
  - `agents/` (demo)
  - `agents_packs/*/agents/` (submodules)
  - dirs from `AGENTFORGE_AGENT_PACKS_DIRS`
- [X] 2.3 Build `AgentRegistry`:
  - deterministic load order
  - deterministic capability index
  - deterministic tie-break rules (agent_id lexical or explicit priority)
- [X] 2.4 Export registry snapshot to `runs/<run_id>/control/registry.json`

Acceptance criteria:
- Registry loads deterministically and errors clearly.
- Private packs optional; core works without them.

---

## Phase 3 — Execution Plane Boundary + Runtime Adapters

- [X] 3.1 Define `ExecutionRequest` and `ExecutionResult`:
  - request: run_id/node_id/agent_id/operation/runtime/inputs/timeout/policy/metadata
  - result: status/produced_artifacts/metrics/error/latency_ms/adapter info
- [X] 3.2 Implement adapters:
  - `PythonRuntimeAdapter` (module:function entrypoint)
  - `CommandRuntimeAdapter` (command template; Node/npm supported)
  - `ContainerRuntimeAdapter` (stub)
- [X] 3.3 Define and enforce operations_policy semantics (guardrails):
  - command allowlist checks
  - fs_scope allowlist checks
  - network allowlist best-effort checks
- [X] 3.4 Define V1 OS support matrix:
  - Unix/macOS only (explicit)
  - path normalization rules for artifacts (POSIX-style)

Acceptance criteria:
- Execution is adapter-driven and policy-checked.
- Adapters do not leak cross-node filesystem coupling.

---

## Phase 4 — Scheduler v1 (Dependencies + Parallelism + Artifact Handoff)

- [X] 4.1 Implement scheduler:
  - nodes become ready when dependencies succeeded
  - execute up to ControlPlan.max_parallel
  - enforce per-agent max_concurrency
  - deterministic tie-break for ready nodes (node_id)
- [X] 4.2 Artifact handoff:
  - downstream reads inputs strictly by manifest refs
  - ingest steps must write snapshot artifacts (determinism boundary)
- [X] 4.3 Failure semantics:
  - node failure blocks downstream unless retry policy allows
  - transient retries only when declared; never infinite
- [X] 4.4 Control-plane persistence:
  - write events for node transitions
  - persist final control snapshot

Acceptance criteria:
- Multi-node runs are deterministic, bounded, and auditable.
- Scheduler correctness proven by unit tests.

---

## Phase 5 — CLI + Scheduled/Event Trigger Support

- [X] 5.1 CLI entrypoints:
  - `agentforge run <pipeline.yaml>` (existing runner path)
  - `agentforge dispatch --agent <agent_id> --request <request.json>`
  - `agentforge resume --run_id <id>`
  - `agentforge status --run_id <id>`
- [X] 5.2 Triggers:
  - `TriggerSpec.kind=manual` for CLI runs
  - `TriggerSpec.kind=schedule` for cron-driven runs (OS cron calls CLI)
  - `TriggerSpec.kind=event` for webhook/manual event triggers
- [X] 5.3 Ensure request payload is stored as an input artifact for reproducibility.

Acceptance criteria:
- V1 supports ad-hoc and scheduled/event-triggered batch runs.
- Trigger metadata and inputs are persisted as artifacts.

---

# Phase 6 — ArXiv Research Agent Migration (Public Example Agent)

Goal:
Migrate the existing ArXiv Research Digest workflow into a **public example agent** that:
- Demonstrates AgentSpec + runtime integration
- Uses manifest-indexed artifacts (Message = Artifact invariant)
- Runs as part of a multi-node ControlPlan
- Serves as a portfolio-quality reference implementation

This phase is post-V1 and assumes Phases 0–5 are complete.
It is intentionally excluded from the V1 release gate.

---

## Design Principles

- The ArXiv agent must live in the **public repo** under `agents/`.
- It must not depend on any private agent packs.
- It should demonstrate:
  - external ingest + snapshot artifact
  - deterministic normalization
  - LLM synthesis via provider abstraction
  - structured output + report artifact
- It must clearly illustrate determinism boundaries for external data.

---

## Target Structure
agents/
arxiv_research/
agent.yaml
entrypoint.py
prompts/
system.md
schemas.py
internal_pipeline.yaml (optional)
tests/


---

## 6.1 Define ArXivResearch AgentSpec

- [X] 6.1.1 Create `agents/arxiv_research/agent.yaml`:
  - identity:
    - agent_id: "arxiv.research"
    - version: "1.0.0"
    - description: "Fetches ArXiv papers by query and produces a structured research digest."
  - intents:
    - research
    - arxiv
    - digest
  - input_contracts:
    - ResearchRequest (Pydantic model)
  - output_contracts:
    - ResearchDigest (Pydantic model)
    - report.md (rendered summary)
  - runtime:
    - runtime: python
    - entrypoint: agents.arxiv_research.entrypoint:run
    - timeout_s: 120
    - max_concurrency: 2
  - operations_policy:
    - terminal_access: none
    - network_access: allowlist
    - network_allowlist:
        - export.arxiv.org
    - fs_scope: restricted to node working directory

Acceptance criteria:
- AgentSpec validates under AgentRegistry.
- No private code required.

---

## 6.2 Define Input / Output Schemas

- [X] 6.2.1 Implement `ResearchRequest`:
  - query: str
  - max_results: int
  - categories: list[str] | None
  - sort_by: "relevance" | "lastUpdatedDate"
  - mode: "live" | "replay"
- [X] 6.2.2 Implement `ResearchPaper`:
  - paper_id
  - title
  - authors
  - abstract
  - categories
  - published
- [X] 6.2.3 Implement `ResearchDigest`:
  - query
  - generated_at_utc
  - papers: list[ResearchPaper]
  - highlights: list[DigestBullet]
- [X] 6.2.4 `DigestBullet`:
  - text
  - cited_paper_ids: list[str]

Acceptance criteria:
- Schemas are Pydantic models.
- JSON serialization deterministic.
- Output contract enforced at runtime.

---

## 6.3 Implement Deterministic Ingest + Snapshot Boundary

- [X] 6.3.1 Ingest step:
  - Fetch ArXiv Atom feed (export.arxiv.org).
  - Parse into structured `ResearchPaper`.
- [X] 6.3.2 Write raw snapshot artifact:
  - `raw_feed.xml`
  - `papers_raw.json`
- [X] 6.3.3 Determinism rule:
  - If `mode=replay`, skip network call and load from snapshot artifact.
  - Snapshot artifact is required input in replay mode.

Acceptance criteria:
- Live mode fetches + snapshots.
- Replay mode produces identical digest given same snapshot.
- Determinism boundary documented in ADR.

---

## 6.4 Implement Synthesis (LLM Provider Abstraction)

- [X] 6.4.1 Use provider interface from Phase 3+:
  - `generate_json(prompt, schema)` → `ResearchDigest`
- [X] 6.4.2 Prompt must:
  - Summarize key contributions.
  - Produce bullet highlights.
  - Require citation via `cited_paper_ids`.
- [X] 6.4.3 Validate:
  - All cited_paper_ids must exist in papers list.
  - Reject uncited highlights.
- [X] 6.4.4 Determinism behavior:
  - replay mode is the contract for deterministic synthesis verification
  - live mode uses pinned model + stable prompt + optional seed (best-effort only)

Acceptance criteria:
- Synthesis output conforms to `ResearchDigest`.
- Missing or invalid citations cause explicit failure.
- Replay-mode synthesis is reproducible in integration tests.

---

## 6.5 Render Report Artifact

- [X] 6.5.1 Render `report.md`:
  - Title
  - Query
  - Table of papers
  - Highlights section with inline citations
- [X] 6.5.2 Write artifacts:
  - `digest.json`
  - `report.md`
  - `sources.json` (paper metadata)

Acceptance criteria:
- Report artifact reproducible from digest.json.
- Markdown references valid paper IDs.

---

## 6.6 Example Multi-Node ControlPlan (Public Demo)

- [X] Create example plan under `examples/arxiv_digest_plan.yaml`:

Nodes:
1) fetch_and_snapshot (arxiv.research, mode=live)
2) synthesize_digest (internal call within agent OR second node)
3) render_report (if separate node)
4) optional: local_write_delivery

Acceptance criteria:
- Example plan runs end-to-end via CLI:
  - `agentforge dispatch --agent arxiv.research --request request.json`
- Artifacts stored under run folder with control-plane state.

---

## 6.7 Tests

- [X] Unit tests:
  - AgentSpec validation
  - Snapshot replay produces identical digest
  - Citation validation rejects invalid references
  - Deterministic ordering of papers
- [X] Integration test:
  - Run in replay mode using fixed snapshot artifact
  - Compare digest.json to expected fixture

Acceptance criteria:
- Tests pass without network in replay mode.
- Public repo test suite remains stable.

---

## 6.8 Portfolio Quality Checklist

- Clear, minimal code.
- No hard-coded secrets.
- LLM provider mocked in tests.
- [X] Example README under `agents/arxiv_research/README.md` explaining:
  - determinism boundary
  - replay mode
  - how to extend agent
- No dependency on private agent packs.

---

## Phase 6 Completion Criteria

- Public ArXiv research agent runs end-to-end.
- Demonstrates:
  - external ingest + snapshot boundary
  - structured contracts
  - LLM synthesis with validation
  - artifact-indexed outputs
  - compatibility with ControlPlan and scheduler
- Serves as canonical example for:
  - OSINT-style ingest
  - Morning brief pipelines
  - CLI-driven research queries

## V1 Acceptance Criteria (Release Gate)

- Deterministic, auditable multi-node execution with persisted control-plane state.
- Registry loads demo agents; private packs via submodules work when present.
- CLI supports run/dispatch/status/resume.
- All tests pass on Unix/macOS.
- Clear ADRs document determinism boundaries, event replay/versioning, and policy semantics.
- Phase 6 deliverables are explicitly out of scope for V1 release.

---

## Stage 2 — Production CLI + Orchestrator Activation (Post-Phase-6)

Goal:
Enable true production use of `agentforge dispatch/status/resume` and execute the public `arxiv.research` agent through the control-plane scheduler + runtime adapters end-to-end.

### Phase 7 — Control Runtime Execution Loop

- [X] 7.1 Build control-plane run executor:
  - load `ControlPlan` + `AgentRegistry` for a run
  - construct `ExecutionRequest` per ready node
  - execute via `RuntimeAdapter` selection from `AgentSpec.runtime`
  - consume `ExecutionResult` and persist node state transitions
- [X] 7.2 Artifact registration bridge:
  - register node outputs in `manifest.json` as `ArtifactRef`
  - enforce unique artifact names and path validation via existing manifest utilities
  - ensure downstream nodes read inputs strictly from manifest refs
- [X] 7.3 Node lifecycle events:
  - append `NODE_READY`, `NODE_STARTED`, `NODE_SUCCEEDED`, `NODE_FAILED`
  - include retry attempt metadata when retrying transient failures
  - persist final `control/snapshot.json` at terminal state

Acceptance criteria:
- A control-plan run executes nodes through scheduler decisions until terminal state.
- Manifest and control event log remain consistent and replayable.

---

### Phase 8 — Agent Plugin Architecture (8a/8b/8c)

- [X] 8a.1 Define plugin execution contract (typed + stable):
  - canonical plugin entrypoint signature:
    - `run(request: ExecutionRequest) -> ExecutionResult`
  - operation dispatch strictly by `request.operation`
  - plugin I/O strictly through manifest-indexed artifacts (no direct coupling)
- [X] 8a.2 Extend/confirm `AgentSpec` plugin metadata fields:
  - `runtime.type` (v1: `python_subprocess`; future: `container`)
  - runtime entrypoint reference for Python plugins
  - operation capability metadata (`capabilities.operations`) with expected input/output artifact names
- [X] 8a.3 Registry/plugin validation:
  - validate plugin metadata completeness at load time
  - validate declared operation names are unique and non-empty
  - fail fast with explicit schema/contract errors

- [ ] 8b.1 Implement ArXiv as a plugin at `agents/arxiv_research/entrypoint.py`:
  - expose canonical `run(request)` entrypoint
  - route operations:
    - `fetch_and_snapshot`
    - `synthesize_digest`
    - `render_report`
    - optional `local_write_delivery` stub (explicitly optional)
- [ ] 8b.2 Bridge operation outputs to `ExecutionResult`:
  - map operation outputs to `produced_artifacts` with validated relative `outputs/...` paths
  - preserve explicit metrics/error fields
  - do not register partial outputs on failed operations (unless explicitly documented)
- [ ] 8b.3 Determinism and input checks:
  - validate required input artifacts from manifest before execution
  - preserve replay-mode deterministic behavior contract
  - surface explicit failure messages (no silent fallback)

- [ ] 8c.1 Introduce runtime adapter seam for future container plugins:
  - keep control-plane execution path runtime-agnostic via `RuntimeAdapter` selection
  - define container runtime contract surface in spec/docs (image/command/env/io contract)
  - if container runtime is not implemented in V1, return explicit unsupported-runtime errors
- [ ] 8c.2 Multi-language plugin interoperability contract:
  - define normalized request/response JSON contract for non-Python plugins
  - require artifact paths and metrics/error fields to match `ExecutionResult` invariants
  - ensure Unix/macOS-only path and policy constraints remain enforced by adapters
- [ ] 8c.3 Tests:
  - unit tests for plugin metadata/registry validation
  - unit tests for ArXiv entrypoint operation routing + failure mapping
  - regression test that unsupported runtime types fail explicitly and safely

Acceptance criteria:
- Adding a new private agent plugin requires only:
  - agent folder/submodule with `agent.yaml` + runtime entrypoint implementation
  - no orchestrator/control-plane code changes for standard operation routing
- `arxiv.research` executes through the plugin contract via `PythonRuntimeAdapter`.
- Runtime adapter seam is ready for containerized and multi-language plugins without architecture changes.

---

### Phase 9 — Real CLI Dispatch Command

- [ ] 9.1 Implement `agentforge dispatch --agent <agent_id> --request <request.json>`:
  - create run directory and initialize manifest/control artifacts
  - persist request payload artifact (`request_json`) and trigger metadata
  - materialize an initial `ControlPlan` for the selected agent
- [ ] 9.2 Plan generation modes:
  - default single-agent/single-plan dispatch path
  - support loading a plan file override (e.g., `examples/arxiv_digest_plan.yaml`) when provided
  - validate agent existence in registry before run start
- [ ] 9.3 Terminal output and exit codes:
  - print run_id on success
  - non-recoverable execution errors return exit code 1
  - internal/runtime failures return exit code 2 with concise error

Acceptance criteria:
- `dispatch` launches real execution (not placeholder) and produces run outputs.
- Resulting run contains manifest + control artifacts + node outputs.

---

### Phase 10 — CLI Status and Resume

- [ ] 10.1 Implement `agentforge status --run_id <id>`:
  - read control snapshot/events/manifest for the run
  - display run terminal/non-terminal status
  - summarize node states and latest event id
- [ ] 10.2 Implement `agentforge resume --run_id <id>`:
  - reload persisted control state and continue schedulable work
  - respect existing retry policy counters/state
  - avoid re-running already-succeeded nodes
- [ ] 10.3 Consistency safeguards:
  - reject resume when run is already terminal
  - clear error messages for missing/invalid run ids
  - keep event log append-only across resume calls

Acceptance criteria:
- Paused/partial runs can be resumed deterministically.
- Status accurately reflects control-plane state at any point.

---

### Phase 11 — Production Smoke + Integration Tests

- [ ] 11.1 CLI integration test:
  - run `dispatch` on `arxiv.research` in replay mode using fixed snapshots
  - assert `digest.json`, `report.md`, `sources.json` are produced
  - assert `request_json` artifact and control artifacts exist
- [ ] 11.2 Resume integration test:
  - simulate interrupted run and resume
  - verify no duplicate artifacts and correct terminal state
- [ ] 11.3 Status integration test:
  - verify status output for running, failed, and succeeded runs
  - verify event/snapshot consistency with manifest step outcomes

Acceptance criteria:
- End-to-end CLI workflow (`dispatch -> status -> resume`) is production-usable.
- Tests prove deterministic replay path with no network access.
