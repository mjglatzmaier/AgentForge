## ArXiv Synthesis Token Overflow Plan

## Purpose

Fix synthesis failures caused by truncated LLM JSON (`finish_reason=length`) with a robust, efficient, and simple design that preserves determinism and existing Control Plane contracts.

---

## Problem Summary

Current synthesis behavior sends all retrieved papers in one prompt and asks for a full `ResearchDigest` output including full paper objects.  
This creates avoidable output token pressure and frequent truncation, even at small `max_results`.

Observed failure pattern:
- provider returns partial JSON
- `finish_reason=length`
- parser raises non-JSON or schema-validation errors
- node fails at `synthesize_digest`

---

## Root Cause (Confirmed)

1. **One-shot global synthesis:** all papers are passed at once.
2. **Overly large response contract:** model is asked to emit full `papers` payload in output.
3. **No token budget guardrail:** no pre-call estimation to cap input/chunk size.
4. **No structured overflow recovery:** no fallback when finish reason indicates truncation.

---

## Goals

1. Eliminate JSON truncation failures in normal operation.
2. Keep implementation simple and maintainable.
3. Preserve replay determinism.
4. Improve throughput/latency via safe parallel chunking where beneficial.
5. Keep artifact-level traceability for debugging and evaluation.

---

## Non-Goals (Initial Rollout)

- No new external orchestration framework.
- No change to Control Plane contracts (`ControlNode -> ExecutionRequest -> RuntimeAdapter`).
- No heavy retrieval/reranking framework introduction.

---

## Design Principles

1. **Minimize output footprint first** (highest leverage).
2. **Compress input before chunking** (best cost/benefit).
3. **Chunk only when needed** (simple default path).
4. **Deterministic merge logic** for chunked outputs.
5. **Explicit overflow handling** keyed on finish reason / parse failure.

---

## Proposed Architecture (Synthesis)

### A) Split output contracts

Introduce a compact model for model output:
- `SynthesisHighlights`:
  - `highlights: list[DigestBullet]`
  - optional concise metadata only

Do **not** ask the model to re-emit full papers.  
Build final `ResearchDigest` in code:
- `query` from config/input context
- `generated_at_utc` locally generated
- `papers` copied deterministically from input `papers_raw`
- `highlights` from model output

Expected impact: largest drop in output tokens and truncation risk.

### B) Input compression layer

Before prompting, map each paper to a compact representation:
- `paper_id`
- `title`
- short abstract snippet (bounded chars/tokens)
- categories
- published

Exclude long author lists/verbose fields unless needed.

### C) Token budget manager

Add estimator + limits:
- max input budget per call
- reserved output budget
- safety margin

If estimated input exceeds budget:
- chunk papers deterministically
- process chunks independently

### D) Chunked synthesis path (map-reduce)

Map step:
- synthesize highlights per chunk (same compact output schema)
- optionally in bounded parallel mode

Reduce step:
- merge highlights across chunks
- dedupe semantically/syntactically
- score/prioritize
- enforce final highlight cap

All tie-breakers deterministic (`paper_id`, timestamp, lexical order).

### E) Overflow recovery path

On parse failure with `finish_reason=length` (or equivalent):
1. retry once with lower output cap / stricter prompt
2. if still failing, fallback to smaller chunk size
3. emit explicit metrics and diagnostics artifact

No silent success-shaped fallback.

---

## Prompting Best Practices

1. Strong JSON-only instruction.
2. Compact schema with minimal required fields.
3. Explicit output cap (`max_highlights`, per-highlight length guidance).
4. Force citation IDs only from provided `paper_id` list.
5. Keep system prompt stable and versioned.

---

## Parallelization Strategy

- Default: sequential for small batches.
- Chunked mode: bounded parallel workers (small fixed cap, deterministic chunk ordering).
- Merge step remains single-threaded deterministic.

Parallelization must not alter semantic output order for identical inputs.

---

## Artifact Plan

Synthesis step outputs:
- `outputs/digest.json` (final contract unchanged)
- `outputs/synthesis_diagnostics.json` (new; debug-safe)
  - token estimates
  - chunk counts/sizes
  - retry count
  - overflow flags
  - finish reasons seen (if available)

Optional intermediate artifacts (debug/eval mode):
- `outputs/chunk_highlights.json`
- `outputs/compressed_papers.json`

---

## Rollout Phases

### Phase T0 — Baseline + Telemetry
- [ ] T0.1 Capture current overflow repro with fixed fixture.
- [ ] T0.2 Add diagnostics collection for finish reason and parse errors.
- [ ] T0.3 Add synthesis metrics fields: input_count, estimated_tokens, overflow_retries.

Acceptance:
- can reproduce and observe overflow root cause with deterministic test.

---

### Phase T1 — Compact Output Contract
- [ ] T1.1 Add `SynthesisHighlights` model.
- [ ] T1.2 Change provider call response model from `ResearchDigest` to compact model.
- [ ] T1.3 Build full `ResearchDigest` in Python from input papers + generated highlights.

Acceptance:
- digest shape unchanged for downstream steps.
- output token size reduced substantially.

---

### Phase T2 — Input Compression
- [ ] T2.1 Add deterministic paper compressor utility.
- [ ] T2.2 Update synthesis prompt to use compressed payload.
- [ ] T2.3 Add compression unit tests (field inclusion, bounds, determinism).

Acceptance:
- compressed payload stable and significantly smaller.

---

### Phase T3 — Budgeting + Adaptive Chunking
- [ ] T3.1 Implement token budget estimator and thresholds.
- [ ] T3.2 Add chunk planner (deterministic chunk boundaries).
- [ ] T3.3 Add chunk map + merge synthesis flow with deterministic merge.

Acceptance:
- large inputs run without truncation.
- repeated replay runs produce identical digest.

---

### Phase T4 — Overflow Recovery & Reliability
- [ ] T4.1 Add overflow retry policy keyed to finish reason/parse failure.
- [ ] T4.2 Add fallback to smaller chunk size.
- [ ] T4.3 Emit diagnostics artifact and explicit failure reasons when exhausted.

Acceptance:
- overflow failures become rare and diagnosable.
- terminal failure messages remain concise and actionable.

---

### Phase T5 — Parallel Chunk Execution (Optional but Recommended)
- [ ] T5.1 Add bounded parallel execution for chunk map stage.
- [ ] T5.2 Keep deterministic merge/tie-break guarantees.
- [ ] T5.3 Add tests proving stable output ordering across runs.

Acceptance:
- better latency on larger batches without determinism regressions.

---

### Phase T6 — Test Matrix + Regression Gates
- [ ] T6.1 Unit tests:
  - compression
  - budgeting
  - chunk planner
  - merge/dedupe
- [ ] T6.2 Integration tests:
  - small (<=5 papers) no overflow
  - medium (20+) chunk path
  - forced truncation simulation path
- [ ] T6.3 Replay parity tests:
  - same snapshot/config => identical digest bytes

Acceptance:
- `python -m pytest` green with dedicated overflow coverage.

---

## Config Surface (Proposed)

Under synthesis `metadata.config`:
- `max_output_tokens` (existing)
- `max_highlights` (new)
- `compression_level` (new; simple enum)
- `chunking_enabled` (new; bool)
- `chunk_size` (new; int)
- `parallel_chunks` (new; int)
- `overflow_retry_limit` (new; int)

Defaults should prioritize safety and simplicity.

---

## Migration / Compatibility

1. Keep existing plans working with defaults.
2. Preserve `digest.json` contract consumed by `render_report`.
3. Gate new behavior behind config defaults so rollout is low risk.

---

## Risks & Mitigations

Risk: quality drop due to compression.  
Mitigation: keep titles + key abstract snippet + categories + paper_id; evaluate against fixtures.

Risk: chunk merge loses global coherence.  
Mitigation: deterministic reduce pass with explicit global dedupe/rank rules.

Risk: more complexity than needed.  
Mitigation: ship T1/T2 first (biggest wins), only add T5 if needed.

---

## Implementation Order (Recommended Minimal Path)

1. T1 (compact output contract)
2. T2 (compression)
3. T4 (overflow recovery)
4. T3 (budgeting/chunking) if still needed
5. T5 (parallel chunks) only after proven value

---

## Definition of Done

- [ ] No frequent truncation failures for normal `max_results` ranges.
- [ ] Replay mode deterministic for synthesis output.
- [ ] `digest.json` contract unchanged and downstream compatible.
- [ ] Overflow diagnostics available in run artifacts.
- [ ] End-to-end dispatch/status/resume tests remain green.
