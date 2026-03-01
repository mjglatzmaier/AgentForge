Step / Node Execution Contract (MVP; MUST follow exactly)

This repository has two execution layers:
1) **Pipeline steps** (legacy runner): StepSpec.ref -> Python callable
2) **Control Plane nodes** (refactor): ControlNode -> ExecutionRequest -> RuntimeAdapter

When implementing a task, follow the contract relevant to that task. Do NOT force everything into StepSpec if the task is Control Plane / adapter work.

---

## A) Pipeline Step Contract (use ONLY for legacy pipeline runner tasks)

- Each step is a Python callable resolved from StepSpec.ref formatted as "module.path:function".
- Callable signature: `def step(ctx: dict[str, Any]) -> dict[str, Any]`

- The step MUST write all output files under: `<step_dir>/outputs/`
- The step MUST return a dict with keys:
  - `"outputs"`: list[{"name": str, "type": str, "path": str}]
      - `"path"` is a POSIX-style relative path from `<step_dir>`, e.g. `"outputs/docs.json"`
  - `"metrics"`: dict[str, int|float|str] (optional; default {})

- The step MUST NOT:
  - compute sha256
  - create ArtifactRef objects
  - read/write manifest.json
  - implement caching
  - write to runs/.cache

Runner responsibilities (MUST implement/own for StepSpec execution):
- Resolve StepSpec.ref to callable and execute sequentially.
- Enforce StepSpec contract:
  - Returned output `"name"` values MUST match StepSpec.outputs exactly (no extras, no missing).
- Validate returned structure:
  - outputs is a list of dicts with keys name/type/path
  - metrics values are JSON-serializable (int/float/str only)
- Validate output paths:
  - "path" must be relative (no leading "/" or drive letters)
  - must not contain ".."
  - must start with "outputs/"
  - file must exist at `<step_dir>/<path>`
- Resolve returned paths relative to step_dir.
- Hash output files (sha256).
- Create `ArtifactRef(producer_step_id=step_id, name=..., type=..., path=..., sha256=...)`
- Register artifacts by unique name within the run (reject duplicates); producer_step_id is metadata only.
- Write step meta.json (valid JSON, never empty) including:
  - step_id, status, started_at, ended_at, metrics, outputs (ArtifactRef list)
- Update manifest.json atomically after each step.

Failure semantics (MUST follow):
- If a step raises an exception:
  - mark step status = failed
  - write meta.json with error info (include error string + traceback excerpt in a safe field)
  - DO NOT register artifacts for that step
  - halt pipeline execution (no further steps)

---

## B) Control Node Contract (use for refactor Control Plane / Execution Plane tasks)

- A ControlNode is NOT a StepSpec. It is executed via:
  - ControlNode -> ExecutionRequest -> RuntimeAdapter -> ExecutionResult.
- The Control Plane MUST NOT execute agent logic directly.
- Runtime adapters MUST enforce operations_policy (guardrails) and OS constraints.

Execution Plane contract:
- Adapter input: `ExecutionRequest` (typed model)
- Adapter output: `ExecutionResult` (typed model), containing:
  - status (success|failed)
  - produced_artifacts: list[ArtifactRef]
  - metrics (json-serializable)
  - error (string + traceback excerpt optional)
  - latency_ms (optional)

Artifact rules (still apply):
- All produced artifacts MUST be written under the node’s step directory:
  - `<run_dir>/steps/<nn_node_id>/outputs/...`
- Downstream nodes consume artifacts ONLY by manifest lookup (Message = Artifact invariant).
- External ingest must write **snapshot artifacts** (determinism boundary). Replay mode must be possible using snapshots.

Failure semantics:
- Node failure:
  - emit control event(s)
  - persist control state
  - do not register partial outputs unless explicitly documented
  - block downstream nodes unless retry policy allows

OS support:
- V1 supports Unix/macOS only. Do not add Windows-specific paths or behavior.

---

You are working in the AgentForge repository.
Use model: GPT-5.3-Codex.

Task:
Complete EXACTLY the following task ID: [Phase 4 (4.1)]
Source of truth file: tasks_refactor3.md (use what the task references).
Do NOT implement anything beyond this task.

Constraints (must follow):
- Keep changes minimal and aligned with docs/architecture.md and .github/copilot-instructions.md.
- Do NOT introduce heavy frameworks (LangChain/LlamaIndex/etc.).
- Use Python 3.11+, type hints, and Pydantic for structured data.
- Agents communicate ONLY via manifest-indexed artifacts (no hardcoded filesystem coupling).
- No global state.
- All changes must include unit tests (pytest). If a change is trivial, add at least one regression test.
- Prefer simple, professional and clean code.

Implementation rules:
1) Before coding, briefly list the files you will modify/create (max 10 lines).
2) Implement the task.
3) Add/extend tests under the relevant tests folders.
4) Run: `python -m pytest`
5) If tests fail, fix them. Do not stop until tests pass.
6) Edit tasks_refactor3.md with an [X] next to each completed work item.

Deliverables in your final response:
A) Summary of what changed (bullet list).
B) List of files changed/added.
C) Commands run and results (pytest output summarized).
D) Suggested Conventional Commit message (title + body).
E) Exact checkbox lines (copy/paste) that should be marked complete in the source task file.
F) Whether docs/architecture.md or .github/copilot-instructions.md require updates (yes/no + why).

Now implement [Phase 4 (4.1)].