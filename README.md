# AgentForge

A lightweight, privacy-first agent orchestration framework for research digestion, evaluation, and autonomous knowledge workflows.

# Overview

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

This project emphasizes reproducibility, and extensibility over heavy abstraction.

# Design Principles

 - Minimal orchestration core (ordered steps, no premature DAG complexity)
 - Explicit artifact contracts via run manifests
 - Agent isolation with clear tool allowlists
 - Structured outputs via typed schemas
 - Provider-agnostic LLM integration
 - Separation between platform (public) and agent implementations (private-capable)
 - Evaluation as a first-class subsystem

# Architecture

AgentForge is organized into four layers:

 - Orchestration
 - YAML-defined pipelines
 - Sequential step execution
 - Step-level caching
 - Run ID–scoped artifact directories
 - Manifest tracking

# Agents
Each agent lives in:

```
agents/<agent_name>/
agent.yaml
prompts/
tools/
src/
```

Agents may run:

 - In-process (Python)
 - As subprocesses
 - As containers (future support)

# Artifact System
Each pipeline run generates:
```
runs/<run_id>/
manifest.json
steps/
logs/
```
Artifacts are indexed and accessed via the manifest rather than direct filesystem coupling.

# Evaluation
The evaluation subsystem provides:

 - Structured metrics
 - RAG quality scoring
 - Regression comparison across runs
 - LLM-as-judge rubric scoring (optional)

Example: Research Digest Pipeline
```
fetch_arxiv -> fetch_rss -> dedupe_rank -> synthesize -> render
```
Output:

 - Structured JSON digest
 - Markdown report
 - Full artifact trace
 - Optional evaluation report

# Why AgentForge?

Modern LLM workflows require more than a single prompt.

AgentForge provides:

 - Deterministic pipeline execution
 - Artifact reproducibility
 - Multi-agent extensibility (agent swarms)
 - Clear separation of concerns
 - Evaluation-ready infrastructure

It is intentionally lightweight and does not depend on heavy agent frameworks.

# Roadmap

 - DAG execution support
 - Containerized agent runtime
 - Advanced evaluation backends
 - Multi-agent orchestration modes
 - Persistent vector retrieval layer
 - Voice-enabled local assistant integration

# Status

- Early-stage platform under active development.
- Research Digest agent available as reference implementation.

License

TBD
