# Task Implementation Template (AgentForge)

Use this template to run one scoped task with high-quality, low-friction execution.

---

## Step / Node Execution Contract (MVP; MUST follow exactly)

This repository has two execution layers:
1) **Pipeline steps** (legacy runner): `StepSpec.ref -> Python callable`
2) **Control Plane nodes** (refactor): `ControlNode -> ExecutionRequest -> RuntimeAdapter`

When implementing a task, follow the contract relevant to that task.  
Do NOT force everything into `StepSpec` if the task is Control Plane / adapter work.

---

## A) Pipeline Step Contract (legacy pipeline runner tasks only)

- Step resolution: `StepSpec.ref` formatted as `"module.path:function"`.
- Callable signature: `def step(ctx: dict[str, Any]) -> dict[str, Any]`

Step requirements:
- Write all output files under: `<step_dir>/outputs/`
- Return:
  - `"outputs"`: `list[{"name": str, "type": str, "path": str}]`
    - `"path"` is POSIX-style relative path from `<step_dir>`, e.g. `"outputs/docs.json"`
  - `"metrics"`: `dict[str, int|float|str]` (optional; default `{}`)

Step must NOT:
- compute sha256
- create `ArtifactRef` objects
- read/write `manifest.json`
- implement caching
- write to `runs/.cache`

Runner responsibilities:
- Resolve and execute steps sequentially.
- Enforce output name contract: returned output names MUST exactly match `StepSpec.outputs`.
- Validate return structure and metrics scalar types.
- Validate output paths:
  - relative only (no leading `/`, no drive letters)
  - no `..`
  - starts with `outputs/`
  - file exists at `<step_dir>/<path>`
- Hash output files (sha256).
- Create/register `ArtifactRef` (unique artifact name within run).
- Write `meta.json` per step with status/timestamps/metrics/outputs.
- Update `manifest.json` atomically after each step.

Failure semantics:
- On exception: mark failed, write error details in `meta.json`, register no artifacts, halt pipeline.

---

## B) Control Node Contract (Control Plane / Execution Plane tasks)

- A `ControlNode` is NOT a `StepSpec`.
- Execution path: `ControlNode -> ExecutionRequest -> RuntimeAdapter -> ExecutionResult`
- Control Plane must not execute agent logic directly.
- Runtime adapters must enforce `operations_policy` + OS/runtime guardrails.

Execution contract:
- Input: typed `ExecutionRequest`
- Output: typed `ExecutionResult` with:
  - `status` (`success|failed`)
  - `produced_artifacts: list[ArtifactRef]`
  - `metrics` (JSON-serializable)
  - `error` / `traceback_excerpt` (optional)
  - `latency_ms` (optional)

Artifact rules:
- Artifacts must be under `<run_dir>/steps/<nn_node_id>/outputs/...`
- Downstream consumes by manifest lookup only (Message = Artifact invariant)
- External ingest writes snapshot artifacts to support replay mode

Failure semantics:
- Emit control event(s), persist control state, avoid partial output registration unless explicitly documented, block downstream unless retry policy allows.

OS support:
- Follow the active target matrix in the source task/docs (default current behavior unless explicitly changed by task scope).

---

## Task Input (fill before running)

- Repository: `AgentForge`
- Model: `GPT-5.3-Codex`
- Task ID: `[0.5]`
- Source of truth file: `tasks/task-refactor-01.md`
- Scope boundary: `Implement only this task; no extra features.`

---

## Constraints (must follow)

- Keep changes minimal and aligned with `docs/architecture.md` and project instructions.
- No heavy frameworks.
- Python 3.11+, type hints, typed schemas (Pydantic where applicable).
- Agents communicate via manifest-indexed artifacts only.
- No global state; no hidden side effects.
- Add/extend pytest coverage for behavior changed.
- Prefer simple, deterministic, professional code.

---

## Implementation Rules (must follow)

1) Before coding, list files to modify/create (max 10 lines).  
2) Implement only the scoped task.  
3) Add/extend tests under relevant test folders.  
4) Run: `python -m pytest`  
5) If tests fail, fix and re-run until passing.  
6) Update source-of-truth checklist items (`[ ]` -> `[X]`) for completed work only.  
7) Do not change unrelated files.

---

## Final Response Format

A) Summary of changes (bullets)  
B) Files changed/added  
C) Commands run + summarized results  
D) Suggested Conventional Commit message (title + body)  
E) Exact checklist lines marked complete in source task file  
F) Whether `docs/architecture.md` or project instructions need updates (yes/no + why)

---

## Prompt Stub (copy/paste and fill)

You are working in the AgentForge repository.  
Use model: GPT-5.3-Codex.

Task:  
Complete EXACTLY task ID: `[0.5]`  
Source of truth file: `tasks/task-refactor-01.md`
Do NOT implement anything beyond this task.

Follow all contracts, constraints, implementation rules, and final response format in `tasks/task-template.md`.
