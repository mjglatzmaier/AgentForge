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

## Phase 2: Orchestrator MVP (Ordered Steps, Deterministic Execution)

Goal:
Implement a minimal, deterministic sequential pipeline runner with strict artifact contracts and no DAG complexity.

All tasks must be small, testable, and mergeable independently.

---

## 2.0 Pipeline YAML Loader (Parse + Validate)

- [X] 2.0.1 Implement load_pipeline(path: str | Path) -> PipelineSpec
    - Read YAML using yaml.safe_load
    - Fail clearly if file not found
    - Fail clearly on YAML parse errors
- [X] 2.0.2 Validate:
    - Root must be mapping/dict
    - Pipeline name non-empty
- [X] 2.0.3 Convert dict -> PipelineSpec using Pydantic
    - Surface validation errors cleanly
- [X] 2.0.4 Unit tests:
    - Valid pipeline loads successfully
    - Duplicate step ids rejected
    - Missing required fields rejected
    - Non-dict root rejected

Acceptance criteria:
- YAML loading is deterministic and produces PipelineSpec.
- Validation errors are clear and anchored to file path.

---

## 2.1 Step Resolver (Callable Import Validation)

- [X] 2.1.1 Implement resolve_ref("module.path:function") -> callable
    - Validate colon format
    - Import module
    - Lookup function
    - Ensure object is callable
- [X] 2.1.2 Raise clear errors for:
    - Missing colon
    - Missing module
    - Missing function
    - Non-callable object
- [X] 2.1.3 Unit tests:
    - Resolves known test function
    - Fails on bad format
    - Fails on missing module/function

Acceptance criteria:
- Step ref resolution deterministic and explicit.
- No silent import failures.

---

## 2.2 Execution Contract Definition (Before Runner Logic)

Define strict MVP step contract:

Callable signature:
    (context: dict) -> dict[str, Any]

Rules:
- Returned keys must exactly match StepSpec.outputs.
- Undeclared outputs -> error.
- Missing declared outputs -> error.
- Empty output allowed only if outputs list empty.

- 2.2.1 Document contract in architecture.md
- 2.2.2 Implement validation helper:
    validate_step_outputs(step: StepSpec, returned: dict)

- 2.2.3 Unit tests:
    - Undeclared output rejected
    - Missing output rejected
    - Correct match accepted

Acceptance criteria:
- Orchestrator enforces declared artifact contract.
- Tool behavior predictable and validated.

---

## 2.3 Runner Skeleton (No Execution Yet)

- 2.3.1 Implement run_pipeline(pipeline_path, base_dir, mode) -> run_id
    - Generate uuid4 run_id
    - Create run layout
    - Write run.yaml (RunConfig)
    - Initialize empty manifest.json
- 2.3.2 Unit tests:
    - run directory created
    - run.yaml valid
    - manifest.json exists and contains correct run_id

Acceptance criteria:
- Running pipeline creates deterministic run directory.
- No step execution yet.

---

## 2.4 Structured Per-Step Logging

- 2.4.1 Implement get_step_logger(log_path: Path)
    - Writes to steps/<step>/logs/step.log
    - Avoid duplicate handlers
- 2.4.2 Unit tests:
    - Logger writes to correct file
    - Repeated creation does not duplicate log entries

Acceptance criteria:
- Logging infrastructure exists before execution logic.

---

## 2.5 Sequential Step Execution (No Cache)

- 2.5.1 Extend runner to:
    - Iterate steps in order
    - Create zero-padded step directory
    - Write meta.json with:
        - step_id
        - started_at
        - ended_at
        - status
        - metrics (empty dict allowed)
        - outputs
    - Call resolved callable
    - Validate returned outputs
    - Write outputs to step_dir/outputs/
    - Compute sha256 for each output
    - Register artifacts in manifest
    - Persist manifest after each step
- 2.5.2 Define failure behavior:
    - On exception:
        - status = failed
        - meta.json written
        - manifest updated with StepResult
        - pipeline halts
    - No artifacts registered on failure
- 2.5.3 Unit tests:
    - Two-step fake pipeline executes in order
    - meta.json valid for each step
    - manifest contains expected artifacts
    - Failure halts execution

Acceptance criteria:
- Deterministic sequential execution works.
- Failure semantics explicit and reproducible.
- All artifacts declared and registered.

---

## 2.6 Cache Key Computation (No Skip Yet)

- 2.6.1 Implement compute_step_cache_key(step, mode, input_artifacts)
    - Stable hash of:
        - step spec (id/kind/ref/config/inputs/outputs)
        - mode
        - input artifact sha256 values (sorted)
- 2.6.2 Unit tests:
    - Same inputs produce same key
    - Different config changes key
    - Different input hash changes key

Acceptance criteria:
- Cache key deterministic and stable.

---

## 2.7 Cache Storage Layer (No Integration Yet)

- 2.7.1 Define shared cache directory:
        runs/.cache/<pipeline_name>/
- 2.7.2 Store:
        cache_key -> serialized ArtifactRef outputs
- 2.7.3 Load cache record if exists
- 2.7.4 Unit tests:
    - Cache record round-trip works
    - Cache miss returns None

Acceptance criteria:
- Cache storage reliable and isolated.

---

## 2.8 Cache Integration (Full Skip Behavior)

- 2.8.1 Before executing step:
    - Compute cache key
    - If hit:
        - Verify cached files exist
        - Verify sha256 matches record
        - Copy or link outputs into new step directory
        - Register artifacts
        - Write meta.json with status=skipped
        - Log cache hit
    - If miss:
        - Execute step normally
        - Write cache record on success
- 2.8.2 Ensure:
    - Failed steps never cached
    - Corrupted cache treated as miss
- 2.8.3 Unit tests:
    - Running pipeline twice reuses cached outputs
    - Second run marks cached steps as skipped
    - Corrupted cache triggers re-execution

Acceptance criteria:
- Running pipeline twice with identical inputs reuses outputs.
- Cache cannot silently corrupt execution.
----

## Phase 2.8: Artifact Identity and Naming Rules

- 2.8.0 Define artifact naming invariant:
    - ArtifactRef.name must be globally unique within a run.
    - producer_step_id stored as metadata only.
    - Manifest lookup by name must be deterministic.
- 2.8.1 Enforce:
    - register_artifact rejects duplicate artifact names.
    - Artifact paths must be relative to run root.
- 2.8.2 Add tests:
    - Duplicate artifact names raise error.
    - Absolute paths rejected.
    - Manifest round-trip preserves relative paths.

Acceptance criteria:
- Artifact identity model is explicit and enforced.
- No ambiguity between step-scoped and run-scoped artifact naming.

---

## Phase 2.9: Step Execution Contract Formalization

- 2.9.0 Define strict MVP tool contract:
    - Callable signature:
        (context: dict) -> dict[str, Any]
    - Returned keys must match StepSpec.outputs.
    - Returning undeclared outputs raises error.
    - Missing declared outputs raises error.
- 2.9.1 Document contract in docs/architecture.md.
- 2.9.2 Add validation layer in runner before artifact registration.
- 2.9.3 Add tests:
    - Undeclared output rejected.
    - Missing declared output rejected.
    - Empty output allowed only if outputs list empty.

Acceptance criteria:
- Step behavior is predictable and validated.
- Orchestrator enforces declared artifact contracts.

---

## Phase 2.10: Failure Semantics and Determinism Guarantees

- 2.10.0 Define failure behavior:
    - On exception:
        - StepStatus = failed
        - meta.json written
        - Manifest updated with StepResult
        - Pipeline execution halts.
    - Failed steps are never cached.
- 2.10.1 Ensure:
    - sha256 mismatch triggers failure.
    - Manifest writes are atomic.
- 2.10.2 Add tests:
    - Tool raising exception marks step failed.
    - No artifacts registered on failure.
    - Subsequent steps not executed.

Acceptance criteria:
- Failure state is explicit and reproducible.
- No partial silent corruption possible.

---

## Phase 2.11: Cache Robustness Hardening

- 2.11.0 Define cache scope:
    - Shared cache directory:
        runs/.cache/<pipeline_name>/
- 2.11.1 On cache hit:
    - Verify cached artifact files still exist.
    - Verify sha256 matches record.
    - If mismatch, treat as cache miss.
- 2.11.2 Ensure:
    - Cache records include pipeline_name.
    - Cache key includes mode.
- 2.11.3 Add tests:
    - Corrupted cache record triggers miss.
    - Different mode produces different cache key.
    - Cache never stores failed steps.

Acceptance criteria:
- Cache cannot silently produce incorrect outputs.
- Cache integrity validated before reuse.

---

## Phase 2.12: Mode Determinism Verification

- 2.12.0 Add test:
    - Same pipeline in prod vs debug produces identical artifacts (except metadata/logs).
- 2.12.1 Define:
    - Mode affects only:
        - logging verbosity
        - metadata fields
    - Mode must not change semantic artifact outputs.
- 2.12.2 Add assertion in runner:
    - mode not passed into tool unless explicitly requested.

Acceptance criteria:
- Mode isolation enforced.
- Evaluation runs reproducible across environments.

---

## Phase 2.13: CLI Entry Point Specification

- 2.13.0 Define minimal CLI:
    - agentforge run <pipeline.yaml> [--mode prod|debug|eval]
    - agentforge eval <run_id>
- 2.13.1 Define exit codes:
    - 0 = success
    - 1 = validation error
    - 2 = runtime failure
- 2.13.2 Add integration test:
    - CLI invocation creates run directory successfully.

Acceptance criteria:
- Platform usable without importing Python modules directly.
- Error behavior consistent and predictable.

---

## Phase 2.14: Runtime Abstraction Boundary (Future-proofing)

- 2.14.0 Introduce execution interface:
    - StepExecutor base class
        - execute(step, context) -> StepResult
- 2.14.1 Current implementation: InProcExecutor.
- 2.14.2 Document extension path for:
    - SubprocessExecutor
    - ContainerExecutor

Acceptance criteria:
- Orchestrator does not depend directly on callable invocation.
- Future runtime models pluggable without refactor.


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
