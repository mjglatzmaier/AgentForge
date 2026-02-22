# AgentForge Task List (v0.1)

## Goal
Build a public, professional research digest agent on top of a minimal orchestration platform:
- ordered-step YAML pipelines
- manifest-indexed artifacts
- agent runtimes (inproc first; subprocess/container later)
- evaluation subsystem (separate module)

## Conventions
- Python 3.11+
- Typed Pydantic models for all structured artifacts
- Agents communicate only via manifest-declared artifacts
- Modes: prod / debug / eval (modes affect verbosity + metadata only)

## Phase 0: Repo hygiene and docs
 - 0.0 Confirm repo name: AgentForge
 - 0.1 README.md (plain text)
 - 0.2 docs/architecture.md (plain text)
 - 0.3 .github/instructions.md (plain text)

## Phase 1: Define contracts and schemas (no LLM calls yet)
- 1.0 Define core Pydantic models in agentforge/contracts/models.py:
    - RunConfig (run_id, timestamp, mode, pipeline_name, git_sha optional)
    - ArtifactRef (name, type, path, sha256, producer_step_id)
    - Manifest (run_id, artifacts[], steps[])
    - StepResult (step_id, status, started_at, ended_at, metrics, outputs[])
    - PipelineSpec (name, steps[])
    - StepSpec (id, kind: tool|agent, ref, inputs, outputs, config)
- 1.1 Define JSON schema stubs in schemas/ (doc.json, digest.json, manifest.json, pipeline.json, agent.json).
    (These can be minimal placeholders; Pydantic is source of truth.)
- 1.2 Implement hashing utilities in agentforge/storage/hashing.py (sha256 for files + json-stable hashing).
- 1.3 Implement run folder layout in agentforge/storage/run_layout.py:
```
    runs/<run_id>/
      run.yaml
      manifest.json
      steps/<nn_step_id>/
        outputs/
        logs/
        meta.json
```
- 1.4 Implement manifest read/write and artifact lookup in agentforge/storage/manifest.py.

Acceptance criteria:
- You can create a run directory + empty manifest deterministically.
- You can register and lookup artifacts by name without hardcoded paths.

## Phase 2: Orchestrator MVP (ordered steps)
- 2.0 Implement Pipeline loader in agentforge/orchestrator/pipeline.py:
    - load YAML -> PipelineSpec
    - validate ordered steps + unique ids
- 2.1 Implement Runner in agentforge/orchestrator/runner.py:
    - create run_id
    - create run directory
    - execute steps sequentially
    - write per-step meta.json
    - append artifacts to manifest.json
- 2.2 Implement simple step cache in agentforge/orchestrator/cache.py:
    - cache key = stable hash(step spec + referenced input artifact hashes + mode)
    - if cache hit, reuse outputs and record status=skipped
- 2.3 Implement structured logging (agentforge/utils/logging.py) and ensure logs go under ```steps/<step>/logs/.```

Acceptance criteria:
- Running a pipeline twice with same inputs reuses cached step outputs.
- Manifest contains artifacts with sha256 and correct paths.

## Phase 3: Research Digest Agent (tools only, no LLM yet)
- 3.0 Implement tools under agents/research_digest/tools:
    - arxiv.py: fetch list of papers (title, authors, abstract, url, published)
    - rss.py: fetch RSS items (title, url, snippet, published)
    - normalize.py: map all sources to a common Doc model
    - dedupe_rank.py: dedupe by url/hash, then rank by simple keyword score
    - render.py: render markdown from a structured Digest model
- 3.1 Implement agent-specific step wrappers in agents/research_digest/src/steps.py
- 3.2 Provide a working pipeline YAML in pipelines/research_digest.yaml that runs:
    fetch_arxiv -> fetch_rss -> normalize -> dedupe_rank -> render
- 3.3 Add minimal tests:
    - agents/research_digest/tests/test_dedupe.py verifies dedupe stability

Acceptance criteria:
- Pipeline produces a markdown digest and a JSON digest without calling any LLM.
- All outputs are registered in manifest.json.

## Phase 4: LLM synthesis (Claude + GPT-5.2) with structured output
- 4.0 Define provider interface in agentforge/providers/base.py:
    - generate_json(prompt, schema) -> BaseModel
- 4.1 Implement OpenAI + Claude clients (stubs initially; env-based API keys).
- 4.2 Add synthesize step:
    - input: top-k docs
    - output: Digest JSON (Pydantic)
    - enforce citation doc_ids in every bullet
- 4.3 Add verifier step (optional in v0.1):
    - checks that each claim has citations
    - flags uncited claims
- 4.4 Update pipeline to:
    fetch_arxiv -> fetch_rss -> normalize -> dedupe_rank -> synthesize -> render

Acceptance criteria:
- Digest JSON conforms to schema.
- Render includes citations referencing doc ids.

## Phase 5: Evaluation module MVP (separate)
- 5.0 Implement eval runner (eval/core/runner.py):
    - load run manifest + digest artifact
    - compute metrics and write runs/<run_id>/eval/metrics.json
- 5.1 Metrics v0:
    - retrieval counts, dedupe rate, freshness histogram
    - citation coverage (% bullets with >=1 citation)
    - redundancy heuristic (simple string similarity)
- 5.2 Implement compare tool (eval/core/compare.py):
    - compare two run_ids, diff metrics, write report
- 5.3 Add eval tests in eval/tests/test_metrics.py.

Acceptance criteria:
- `python -m eval.core.runner --run_id <id>` produces metrics.json.
- `python -m eval.core.compare --a <id1> --b <id2>` produces diff report.

## Phase 6: Polish
- 6.0 Add CLI entrypoints (later) for:
    - agentforge run <pipeline.yaml>
    - agentforge eval <run_id>
- 6.1 Add examples + screenshots + LinkedIn-ready project summary.
- 6.2 Optional: add FAISS/Chroma retrieval for local archive search.