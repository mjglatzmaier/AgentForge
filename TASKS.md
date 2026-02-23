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

- 2.0 Pipeline YAML loader (parse + validate)
  - Implement in agentforge/orchestrator/pipeline.py:
    - load_pipeline(path: str|Path) -> PipelineSpec
    - parse YAML -> dict -> PipelineSpec (Pydantic validate)
    - validate:
      - pipeline name non-empty
      - steps ordered as provided
      - step ids unique (PipelineSpec already checks; ensure load surfaces good errors)
  - Add unit tests:
    - valid pipeline yaml loads to PipelineSpec
    - duplicate step ids rejected
    - missing required fields rejected

- 2.1 Step function resolver (import + callable validation)
  - Implement in agentforge/orchestrator/pipeline.py or a new agentforge/orchestrator/resolve.py:
    - resolve_ref("module.path:function") -> callable
    - validate ref format includes colon
    - raise helpful errors if module/function missing
  - Add unit tests:
    - resolves a known local test function
    - fails on bad format
    - fails on missing function

- 2.2 Runner skeleton (create run + initialize manifest)
  - Implement in agentforge/orchestrator/runner.py:
    - run_pipeline(pipeline_path: str|Path, base_dir: str|Path, mode: Mode) -> run_id
    - create run_id (uuid4 string)
    - create run layout (create_run_layout)
    - write run.yaml (RunConfig dumped to YAML)
    - init_manifest(manifest_json, run_id)
    - returns run_id (no step execution yet)
  - Add unit tests:
    - run creates runs/<run_id>/ with steps/ directory
    - run.yaml exists and is valid YAML
    - manifest.json exists and is valid JSON with correct run_id

- 2.3 Runner step execution (ordered, tool-only, no cache)
  - Extend runner.py:
    - execute steps sequentially
    - for each step:
      - create step_dir (00_<step_id>/)
      - write meta.json (valid JSON) including step_id/status/timestamps/metrics/outputs
      - call resolved function:
        - convention for MVP: callable signature (context: dict) -> dict[str, Any]
        - context includes: run_id, mode, run_dir, step_dir, manifest (in-memory), inputs (artifact refs)
      - capture outputs as artifacts:
        - write outputs into step_dir/outputs/
        - compute sha256 for output files
        - register artifacts in manifest with compound key (producer_step_id, name)
      - save manifest after each step
    - define a minimal “tool output contract” for MVP (documented in architecture.md later)
  - Add unit tests:
    - create a fake pipeline with 2 local tool functions that write files
    - verify step meta.json exists and is valid JSON
    - verify manifest contains expected artifacts with sha256 and correct relative paths

- 2.4 Structured logging helper (per-step logs)
  - Implement agentforge/utils/logging.py:
    - get_step_logger(log_path: Path) -> logging.Logger
    - logs go to steps/<step>/logs/step.log (or named file)
    - avoid duplicate handlers when called multiple times
  - Integrate into runner step loop:
    - each step creates logger writing under its logs dir
    - log start/end, cache hit/miss (later), artifact writes
  - Add unit tests:
    - logger writes to expected file
    - repeated creation does not duplicate log lines (no duplicate handlers)

- 2.5 Cache key computation (no skip behavior yet)
  - Implement agentforge/orchestrator/cache.py:
    - compute_step_cache_key(step: StepSpec, mode: Mode, input_artifacts: list[ArtifactRef]) -> str
    - key uses stable hash of:
      - step spec (id/kind/ref/config/inputs/outputs)
      - mode
      - input artifact sha256 values (sorted)
  - Add unit tests:
    - same inputs produce same key
    - different config changes key
    - different input artifact hash changes key

- 2.6 Step cache storage (persisted mapping)
  - Implement in cache.py:
    - cache directory convention: runs/<run_id>/.cache/ (or runs/.cache/<pipeline_name>/)
    - write cache record JSON:
      - cache_key -> list of ArtifactRef outputs (and optionally meta)
    - load cache record if exists
  - Add unit tests:
    - cache record round trip read/write
    - cache miss returns None
    - cache hit returns stored ArtifactRefs

- 2.7 Cache skip integration (full acceptance criteria)
  - Integrate cache into runner:
    - before executing step:
      - compute key
      - if hit: reuse outputs (copy or link) into current run’s step outputs dir
      - register artifacts, write meta.json with status=skipped, and log cache hit
    - if miss: execute and then write cache record
  - Add unit tests:
    - run pipeline twice with same inputs reuses cached outputs
    - second run records status=skipped for cached steps
    - manifest artifacts match expected sha256 and paths

Acceptance criteria (Phase 2):
- Running a pipeline twice with same inputs reuses cached step outputs.
- Manifest contains artifacts with sha256 and correct paths (relative to run dir).
- meta.json files are valid JSON (never empty) for every step.

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