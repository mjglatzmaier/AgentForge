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

- [X] 1.2 Pydantic models: StepSpec and PipelineSpec
   - [X]    - Define StepSpec:
   - [X]      - id: str
   - [X]      - kind: StepKind
   - [X]      - ref: str
   - [X]      - inputs: list[str] = []
   - [X]      - outputs: list[str] = []
   - [X]      - config: dict[str, Any] = {}
   - [X]    - Define PipelineSpec:
   - [X]      - name: str
   - [X]      - steps: list[StepSpec]
   - [X]    - Add validation:
   - [X]      - Unique step IDs
   - [X]      - Non-empty step IDs
   - [X]    - Add unit tests:
   - [X]      - Duplicate step IDs rejected
   - [X]      - Defaults handled correctly

- [X] 1.3 Pydantic models: StepResult and Manifest
   - [X]    - Define StepResult:
   - [X]      - step_id: str
   - [X]      - status: StepStatus
   - [X]      - started_at: datetime
   - [X]      - ended_at: datetime
   - [X]      - metrics: dict[str, float|int|str] = {}
   - [X]      - outputs: list[ArtifactRef] = []
   - [X]    - Define Manifest:
   - [X]      - run_id: str
   - [X]      - artifacts: list[ArtifactRef] = []
   - [X]      - steps: list[StepResult] = []
   - [X]    - Add helper methods:
   - [X]      - get_artifact(name)
   - [X]      - require_artifact(name)
   - [X]    - Add unit tests:
   - [X]      - Artifact lookup works
   - [X]      - require_artifact raises on missing
   - [X]      - StepResult fields validate

- [X] 1.4 JSON schema stubs in schemas/
   - [X]    - Create minimal placeholder schemas:
   - [X]      - schemas/doc.json
   - [X]      - schemas/digest.json
   - [X]      - schemas/manifest.json
   - [X]      - schemas/pipeline.json
   - [X]      - schemas/agent.json
   - [X]    - Pydantic models remain source of truth.
   - [X]    - No behavioral tests required (optional existence test).

- [X] 1.5 Hashing utilities
   - [X]    - Implement in agentforge/storage/hashing.py:
   - [X]      - sha256_file(path)
   - [X]      - sha256_str(s)
   - [X]      - stable_json_dumps(obj) (sorted keys, deterministic)
   - [X]      - sha256_json(obj)
   - [X]    - Ensure stable hashing for:
   - [X]      - dicts with different key order
   - [X]      - Pydantic models (via model_dump)
   - [X]    - Add unit tests:
   - [X]      - Stable hash equality for permuted dict keys
   - [X]      - Known file hash test
   - [X]      - Model hash consistency

- [X] 1.6 Run folder layout
   - [X]    - Implement in agentforge/storage/run_layout.py:
   - [X]      - create_run_layout(base_dir, run_id)
   - [X]      - create_step_dir(layout, step_index, step_id)
   - [X]    - Directory structure must match:
   - [X]      runs/<run_id>/
   - [X]        run.yaml
   - [X]        manifest.json
   - [X]        steps/<nn_step_id>/
   - [X]          outputs/
   - [X]          logs/
   - [X]          meta.json
   - [X]    - Step directories zero-padded (e.g. 00_fetch_arxiv).
   - [X]    - Add unit tests:
   - [X]      - Folder structure created correctly
   - [X]      - Step folder naming verified

- [X] 1.7 Manifest read/write and artifact registration
   - [X]    - Implement in agentforge/storage/manifest.py:
   - [X]      - load_manifest(path)
   - [X]      - save_manifest(path, manifest) (atomic write)
   - [X]      - register_artifact(manifest, artifact)
   - [X]      - lookup_artifact(manifest, name)
   - [X]    - Enforce unique artifact names.
   - [X]    - Add unit tests:
   - [X]      - Manifest round-trip read/write
   - [X]      - Artifact lookup success
   - [X]      - Duplicate artifact names rejected

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