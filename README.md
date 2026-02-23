# AgentForge

A lightweight, privacy-first agent orchestration framework for research digestion, evaluation, and autonomous knowledge workflows.

## Overview

AgentForge is a minimal but professional agent platform designed to support:

- YAML-defined pipeline orchestration
- Modular, provider-agnostic agents
- Structured artifact storage with run manifests
- Local-first execution with optional frontier model integration
- Built-in evaluation backends
- Reproducible research workflows

The initial reference implementation includes a Research Digest Agent that:

- Fetches arXiv and RSS sources
- Normalizes and deduplicates documents
- Ranks relevance
- Synthesizes structured digests
- Stores artifacts with full traceability
- Supports evaluation and regression comparison

## Design Principles

1. Minimal orchestration core (ordered steps only in MVP)
2. Explicit artifact contracts via run manifests
3. Agent isolation with clear tool allowlists
4. Structured outputs via typed schemas
5. Provider-agnostic LLM integration
6. Evaluation as a first-class subsystem

------------------------------------------------------------------

## Build and Development Setup

Requirements

- Python 3.11+
- Git
- Virtual environment recommended

Initial Setup

1. Create and activate a virtual environment:
```bash
   python -m venv .venv
   source .venv/bin/activate   (macOS/Linux)
   .venv\Scripts\activate      (Windows)
```
2. Install dependencies:
```bash
   pip install -e .[dev]
```
3. Verify installation:
```bash
   python -m pytest
```
------------------------------------------------------------------

## Running a Pipeline (coming in Phase 2)

Planned command:
```bash
   python -m agentforge run pipelines/research_digest.yaml
```
This will:

- Generate a new run_id
- Create a runs/<run_id>/ directory
- Execute ordered steps
- Produce structured artifacts
- Write a manifest.json

------------------------------------------------------------------

## Running Evaluation (coming in Phase 5)

Planned command:
```
   python -m eval.core.runner --run_id <run_id>
```
This will:

- Load run manifest
- Compute metrics
- Write eval results under runs/<run_id>/eval/

------------------------------------------------------------------

## Project Structure
```
agentforge/
  contracts/      Core Pydantic models
  orchestrator/   Pipeline execution logic
  storage/        Manifest and artifact indexing
  providers/      LLM provider abstraction
  utils/          Shared utilities

agents/
  research_digest/
    prompts/
    tools/
    src/

pipelines/
  research_digest.yaml

eval/
  metrics/
  core/

runs/
  (generated artifacts)
```
------------------------------------------------------------------

## Status

Active development.
Phase 1 focuses on contracts, hashing, run layout, and manifest system.

## License

MIT