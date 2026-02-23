Use model: GPT-5.3-Codex.

You are working in the AgentForge repository.

Task:
Do a documentation + light linting sweep focused on clarity and maintainability, with minimal churn.

Scope (STRICT):
- Only touch files under:
  - agentforge/
  - agents/ (only if needed for step tool contract examples)
  - docs/ (only if a 1-2 paragraph clarification is truly necessary)
- Do NOT restructure directories.
- Do NOT rename public functions/classes unless clearly incorrect.
- Do NOT change behavior unless it fixes a bug or a clear correctness issue.
- Keep diffs small and localized.

Documentation goals:
- Add module docstrings (1-4 lines) to key modules that define purpose + invariants.
- Add class/function docstrings where behavior/invariants matter:
  - contracts/models.py (especially Manifest + PipelineSpec + StepSpec)
  - storage/hashing.py (what inputs are supported; determinism requirements)
  - storage/run_layout.py (what it creates; what it intentionally does NOT create)
  - storage/manifest.py (init/load/save semantics; compound key identity)
  - orchestrator modules (pipeline loader, resolver, runner, cache)
- Add short inline comments only where intent is non-obvious (avoid over-commenting).
- Ensure docstrings explain:
  - artifact identity is (producer_step_id, name)
  - manifest.json and meta.json must never be empty/invalid JSON
  - cache is stored outside runs (runs/.cache/...)

Light linting goals:
- Run ruff and fix ONLY safe issues:
  - unused imports
  - obvious typing cleanup
  - minor simplifications
- Do NOT apply broad formatting changes or refactors.
- Do NOT change line-length policy.
- Preserve existing public API.

Testing requirements:
- Run:
  - ruff check .
  - python -m pytest
- If ruff finds issues that require large refactors, fix only the smallest safe subset and report the remaining items.

Implementation steps:
1) Identify 6-12 files that most need docstrings/comments and list them.
2) Apply docstrings/comments + minimal lint fixes.
3) Run ruff and pytest. Fix failures.
4) Provide a final summary.

Deliverables:
A) Summary of doc improvements (bullet list).
B) List of files changed.
C) Commands run and results (ruff + pytest summarized).
D) Suggested Conventional Commit message (title + body).
E) Any remaining lint warnings you intentionally did not fix (and why).
F) Whether docs/architecture.md or .github/instructions.md needs updates (yes/no + reason).

Now implement this documentation + light linting sweep.