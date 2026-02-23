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
- [X] 1.0 Core enums and primitives
   - [X]    - Add enums in agentforge/contracts/models.py:
   - [X]      - Mode (prod | debug | eval)
   - [X]      - StepKind (tool | agent)
   - [X]      - StepStatus (success | failed | skipped)
   - [X]    - Add minimal shared type aliases if needed.
   - [X]    - Add unit tests under agentforge/tests/:
   - [X]      - Validate enum parsing and serialization.
   - [X]      - Ensure invalid values raise validation errors.

- [X] 1.1 Pydantic models: RunConfig and ArtifactRef
   - [X]    - Define RunConfig:
   - [X]      - run_id: str
   - [X]      - timestamp: datetime (timezone-aware)
   - [X]      - mode: Mode
   - [X]      - pipeline_name: str
   - [X]      - git_sha: Optional[str]
   - [X]    - Define ArtifactRef:
   - [X]      - name: str
   - [X]      - type: str
   - [X]      - path: str
   - [X]      - sha256: str
   - [X]      - producer_step_id: str
   - [X]    - Add unit tests:
   - [X]      - Valid construction
   - [X]      - Missing required fields rejected
   - [X]      - Datetime handling validated

- 1.2 Pydantic models: StepSpec and PipelineSpec
  - Define StepSpec:
    - id: str
    - kind: StepKind
    - ref: str
    - inputs: list[str] = []
    - outputs: list[str] = []
    - config: dict[str, Any] = {}
  - Define PipelineSpec:
    - name: str
    - steps: list[StepSpec]
  - Add validation:
    - Unique step IDs
    - Non-empty step IDs
  - Add unit tests:
    - Duplicate step IDs rejected
    - Defaults handled correctly

- 1.3 Pydantic models: StepResult and Manifest
  - Define StepResult:
    - step_id: str
    - status: StepStatus
    - started_at: datetime
    - ended_at: datetime
    - metrics: dict[str, float|int|str] = {}
    - outputs: list[ArtifactRef] = []
  - Define Manifest:
    - run_id: str
    - artifacts: list[ArtifactRef] = []
    - steps: list[StepResult] = []
  - Add helper methods:
    - get_artifact(name)
    - require_artifact(name)
  - Add unit tests:
    - Artifact lookup works
    - require_artifact raises on missing
    - StepResult fields validate

- 1.4 JSON schema stubs in schemas/
  - Create minimal placeholder schemas:
    - schemas/doc.json
    - schemas/digest.json
    - schemas/manifest.json
    - schemas/pipeline.json
    - schemas/agent.json
  - Pydantic models remain source of truth.
  - No behavioral tests required (optional existence test).

- 1.5 Hashing utilities
  - Implement in agentforge/storage/hashing.py:
    - sha256_file(path)
    - sha256_str(s)
    - stable_json_dumps(obj) (sorted keys, deterministic)
    - sha256_json(obj)
  - Ensure stable hashing for:
    - dicts with different key order
    - Pydantic models (via model_dump)
  - Add unit tests:
    - Stable hash equality for permuted dict keys
    - Known file hash test
    - Model hash consistency

- 1.6 Run folder layout
  - Implement in agentforge/storage/run_layout.py:
    - create_run_layout(base_dir, run_id)
    - create_step_dir(layout, step_index, step_id)
  - Directory structure must match:
    runs/<run_id>/
      run.yaml
      manifest.json
      steps/<nn_step_id>/
        outputs/
        logs/
        meta.json
  - Step directories zero-padded (e.g. 00_fetch_arxiv).
  - Add unit tests:
    - Folder structure created correctly
    - Step folder naming verified

- 1.7 Manifest read/write and artifact registration
  - Implement in agentforge/storage/manifest.py:
    - load_manifest(path)
    - save_manifest(path, manifest) (atomic write)
    - register_artifact(manifest, artifact)
    - lookup_artifact(manifest, name)
  - Enforce unique artifact names.
  - Add unit tests:
    - Manifest round-trip read/write
    - Artifact lookup success
    - Duplicate artifact names rejected

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