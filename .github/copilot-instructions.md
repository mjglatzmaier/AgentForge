# AgentForge Development Instructions
## Dev models
- Default development model: GPT-5.3-Codex.
- Use Claude Opus for architectural review or adversarial critique.

## Purpose

AgentForge is a minimal, professional agent orchestration framework. All code must prioritize clarity, determinism, and architectural discipline over abstraction or novelty.

## Build and Environment Assumptions

- The Python virtual environment is already created and activated.
- Dependencies are already installed via:
    pip install -e .[dev]
- Tests are executed with:
    python -m pytest
- Linting (optional) may use:
    ruff check .
- Type checking (optional) may use:
    mypy agentforge

When implementing tasks:
- Do NOT add environment setup steps.
- Do NOT modify pyproject.toml unless explicitly required.
- Always run tests before concluding a task.
- A task is not complete unless tests pass.

## Core Principles

 - Keep the orchestrator simple.
 - Do not introduce DAG complexity unless explicitly required.
 - Do not add external frameworks (LangChain, etc.) unless justified.

Preserve strict separation between:

 - platform core
 - agents
 - evaluation
 - Avoid implicit filesystem coupling.
 - All artifacts must be declared and indexed in manifest.json.
 - All LLM outputs must use structured schemas (Pydantic models).
 - Agents must be provider-agnostic.
 - Prefer explicit over magical abstractions.
 - Keep dependencies minimal.

## Code Style

 - Python 3.11+
 - Use type hints everywhere.
 - Use Pydantic for structured data.
 - Avoid global state.
 - Avoid hidden side effects.
 - Keep functions small and composable.
 - Write deterministic utilities where possible.

## Architecture Rules

 - Orchestrator must not depend on specific agent logic.
 - Agents must not directly depend on orchestrator internals.
 - Agents communicate only via declared artifacts.
 - Evaluation must not modify production pipeline behavior.
 - Caching must be input-hash based and explicit.

 ## Precommit Checklist
 Every change must:
- 1. Include unit tests.
- 2. Maintain or increase test coverage.
- 3. Avoid introducing unused dependencies.

## Execution Modes

All agents must support:

 - prod mode
 - debug mode
 - eval mode

Modes may affect:

 - verbosity
 - metadata logging
 - artifact retention
 - Modes must not alter semantic output.

## Dependency Rules

Before adding a dependency:

 - Justify its necessity.
 - Confirm it cannot be implemented cleanly in under ~200 lines.
 - Avoid framework lock-in.

## Commit Philosophy

 - Small, incremental commits.
 - One architectural change per commit.
 - No large, sweeping rewrites.

## Goal

AgentForge should look like a clean internal platform built by a senior engineer, not a hobby project or framework experiment.