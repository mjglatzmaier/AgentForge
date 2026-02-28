Step Tool Contract (MVP; MUST follow exactly)

- Each step is a Python callable resolved from StepSpec.ref formatted as "module.path:function".
- Callable signature: def step(ctx: dict[str, Any]) -> dict[str, Any]

- The step MUST write all output files under: <step_dir>/outputs/
- The step MUST return a dict with keys:
  - "outputs": list[{"name": str, "type": str, "path": str}]
      - "path" is a POSIX-style relative path from <step_dir>, e.g. "outputs/docs.json"
  - "metrics": dict[str, int|float|str] (optional; default {})

- The step MUST NOT:
  - compute sha256
  - create ArtifactRef objects
  - read/write manifest.json
  - implement caching
  - write to runs/.cache

Runner responsibilities (MUST implement/own):
- Resolve StepSpec.ref to callable and execute sequentially.
- Enforce StepSpec contract:
  - Returned output "name" values MUST match StepSpec.outputs exactly (no extras, no missing).
- Validate returned structure:
  - outputs is a list of dicts with keys name/type/path
  - metrics is JSON-serializable (int/float/str only)
- Validate output paths:
  - "path" must be relative (no leading "/" or drive letters)
  - must not contain ".."
  - must start with "outputs/"
  - file must exist at <step_dir>/<path>
- Resolve returned paths relative to step_dir.
- Hash output files (sha256).
- Create ArtifactRef(producer_step_id=step_id, name=..., type=..., path=..., sha256=...)
- Register artifacts by unique name within the run (reject duplicates); producer_step_id is metadata only.
- Write step meta.json (valid JSON, never empty) including:
  - step_id, status, started_at, ended_at, metrics, outputs (ArtifactRef list)
- Update manifest.json atomically after each step.

Failure semantics (MUST follow):
- If a step raises an exception:
  - mark step status = failed
  - write meta.json with error info (include error string/traceback in a safe field)
  - DO NOT register artifacts for that step
  - halt pipeline execution (no further steps)
- Failed steps are never cached (when cache is added later).

You are working in the AgentForge repository.
Use model: GPT-5.3-Codex.

Task:
Complete TASKS.md item [Phase 4.1] ([Phase 4.1]).
Do NOT implement anything beyond this task.

Constraints (must follow):
- Keep changes minimal and aligned with docs/architecture.md and .github/copilot-instructions.md.
- Do NOT introduce heavy frameworks (LangChain/LlamaIndex/etc.).
- Use Python 3.11+, type hints, and Pydantic for structured data.
- Agents communicate ONLY via manifest-indexed artifacts (no hardcoded filesystem coupling).
- No global state.
- All changes must include unit tests (pytest). If a change is trivial, add at least one regression test.
- Prefer simple, professional and clean code when possible.

Implementation rules:
1) Before coding, briefly list the files you will modify/create (max 10 lines).
2) Implement the task.
3) Add/extend tests under the relevant tests folders.
4) Run: python -m pytest
5) If tests fail, fix them. Do not stop until tests pass.

Deliverables in your final response:
A) Summary of what changed (bullet list).
B) List of files changed/added.
C) Commands run and results (pytest output summarized).
D) Suggested Conventional Commit message (title + body).
E) Exact TASKS.md checkbox lines that should be marked complete.
F) Whether docs/architecture.md or .github/copilot-instructions.md require updates (yes/no + why).
G) Update tasks.md by marking [x] next to each task and subtask completed.

Now implement [Phase 4.1].