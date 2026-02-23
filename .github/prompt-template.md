You are working in the AgentForge repository.
Use model: GPT-5.3-Codex.

Task:
Complete TASKS.md item [TASK_ID] ([SHORT TASK NAME]).
Do NOT implement anything beyond this task.

Constraints (must follow):
- Keep changes minimal and aligned with docs/architecture.md and .github/copilot-instructions.md.
- Do NOT introduce heavy frameworks (LangChain/LlamaIndex/etc.).
- Use Python 3.11+, type hints, and Pydantic for structured data.
- Agents communicate ONLY via manifest-indexed artifacts (no hardcoded filesystem coupling).
- No global state.
- All changes must include unit tests (pytest). If a change is trivial, add at least one regression test.

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

Now implement [TASK_ID].