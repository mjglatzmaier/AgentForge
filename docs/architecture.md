# AgentForge Architecture

## Purpose

AgentForge is a minimal agent orchestration platform designed to support reproducible LLM workflows with structured artifact tracking and evaluation.
The architecture prioritizes clarity, determinism, and extensibility over framework abstraction.

## High-Level Model

AgentForge consists of five core components:

 - Pipeline Orchestrator
 - Agent Runtime Layer
 - Artifact and Manifest System
 - Tooling Interface
 - Evaluation Subsystem 
 - Pipeline Orchestrator

Pipelines are defined in YAML and consist of ordered steps.
Each step specifies:

 - id
 - agent or tool
 - inputs
 - outputs
 - optional configuration parameters

Execution is strictly sequential (no DAG in MVP). The orchestrator is responsible for:

 - Generating a unique run_id
 - Creating run directory structure
 - Executing steps in order
 - Passing artifacts between steps
 - Writing run metadata
 - Performing step-level caching
 - Logging execution details
 - Agent Runtime Layer
 - Agents are modular units defined under:
 - ```agents/<agent_name>/```

## Step Execution Contract (MVP)

Each `StepSpec.ref` resolves to a Python callable with signature:

`(context: dict) -> dict[str, Any]`

Each step return payload must be a dict with:

 - `outputs`: list of objects with keys `name`, `type`, `path`
 - `metrics`: optional dict with scalar JSON values (`int | float | str`)

The orchestrator validates output names against `StepSpec.outputs` before any artifact registration:

 - Returned output names must exactly match declared output names.
 - Undeclared outputs are rejected.
 - Missing declared outputs are rejected.
 - Empty output is valid only when `StepSpec.outputs` is empty.

Each agent contains:

 - agent.yaml (metadata and runtime definition)
 - prompts/
 - tools/
 - src/ (optional code)
 - tests/ (optional)

Agent runtime modes:

 - inproc (Python callable)
 - subprocess (command execution)
 - container (future support)

Agents communicate exclusively through declared artifacts. Agents must:

 - Accept structured input
 - Produce structured output (typed schema)
 - Avoid implicit filesystem coupling
 - Artifact and Manifest System

Each run creates:

 - ```runs/<run_id>/```

Structure:

```
runs/<run_id>/
run.yaml
manifest.json
steps/<step_id>/
outputs/
logs/
meta.json
```

Artifacts are indexed in manifest.json and accessed by name.
Agents must request artifacts through manifest lookup rather than hardcoded paths.
This ensures:

 - Explicit dependencies
 - Reproducibility
 - Traceability
 - Clean A2A communication 
 - Tooling Interface

Tools are defined per agent and explicitly allowlisted.
Each tool defines:

 - name
 - input schema
 - output schema
 - implementation location
 - Tool calls are logged in step meta.json.
 - Tools must be deterministic where possible.

## Evaluation Subsystem

Evaluation is implemented as a separate module.
Evaluation responsibilities:

 - Metric computation
 - Run comparison
 - Regression detection
 - Rubric-based scoring
 - Retrieval quality scoring

Evaluation operates over completed runs and does not modify primary pipeline behavior.

## Execution Modes

Agents and pipelines support modes:

 - prod: minimal logging, optimized for regular execution
 - debug: verbose logging, prompt storage, intermediate artifacts
 - eval: deterministic settings, extended metadata

Modes affect only logging verbosity and metadata fields. Modes must not change
semantic artifact outputs. The orchestrator does not pass mode into step tool
context unless explicitly requested by step configuration.

## Design Constraints

 - No implicit global state
 - All artifacts must be declared
 - All steps must be reproducible
 - Provider-agnostic LLM abstraction
 - Minimal external framework dependencies
 - Future Extensions
 - DAG execution
 - Distributed execution
 - Containerized agent runtime
 - Advanced RAG backends
 - Streaming agent communication
