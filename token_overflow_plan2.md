## ArXiv Retrieval → Rerank → Synthesis (Token-Safe, Deterministic) — Drop-in Plan (copilot-cli)

### Intent
Support **high-recall retrieval (up to 200 papers)**, deterministic **top-k rerank (k≈10)**, and **token-safe synthesis** that never depends on emitting full paper objects from the LLM.

### Guiding Rules (keep it simple / high ROI)
- **Never ask the LLM to re-emit full papers.** LLM outputs *highlights only*.
- **Always compress inputs** to bounded snippets before any LLM call.
- **Prefer truncation over chunking.** Only chunk if you still overflow at k≈10.
- **No parallelization** in v1 (determinism + low ROI).
- **Deterministic everywhere:** stable sorting, fixed tie-breakers, stable timestamps, stable prompts.

---

## Pipeline Overview

### Step 1 — Retrieve (High recall)
- Retrieve up to `max_results=200` from ArXiv (or your retrieval backend).
- Snapshot the retrieved list in an artifact (`papers_raw.json`) so replay is deterministic.

**Artifact**
- `outputs/papers_raw.json`: full provider fields (as returned), in stable order

---

### Step 2 — Rerank (Top-k)
- Rerank retrieved papers to `k≈10` using a deterministic scoring function.
- Keep this step independent from synthesis so you can iterate on ranking without touching prompts.

**Minimal viable reranker (high ROI)**
- Use a **weighted linear scorer** with deterministic features:
  - query/category match (exact / overlap)
  - recency (published date)
  - keyword hits in title + abstract snippet
  - optional: arXiv primary category priority list per research area
- Tie-break with `paper_id` lexical order.

**Artifacts**
- `outputs/rerank_scores.json`: list[{paper_id, score, feature_breakdown}]
- `outputs/papers_topk.json`: top-k papers (full fields copied from `papers_raw.json`) in final order

> Optional later upgrade (only if needed): swap scoring core to a cross-encoder / LLM pairwise reranker.
> Keep the output contract identical: `papers_topk.json` + `rerank_scores.json`.

---

### Step 3 — Synthesize (Token-safe)
- Input: `papers_topk.json` (k≈10).
- Create a **compressed prompt payload** (bounded snippets).
- Call LLM once to produce **SynthesisHighlights** only.
- Assemble final `ResearchDigest` in code by copying papers deterministically from `papers_topk.json`.

**Model Output Contract (compact)**
`SynthesisHighlights`:
- `highlights`: list of objects:
  - `text`: concise bullet (hard length guidance)
  - `paper_ids`: list[str] (must be subset of provided ids)

**Final Digest Contract**
- `query`: from config/input
- `generated_at_utc`: from `run_started_at_utc` (captured once at run start; replay uses same value)
- `papers`: copied from `papers_topk.json` (full objects)
- `highlights`: from model output

**Artifacts**
- `outputs/digest.json` (unchanged downstream contract)
- `outputs/synthesis_diagnostics.json` (new, debug-safe)
  - counts: retrieved_count, topk_count
  - estimates: prompt_chars, est_prompt_tokens
  - applied_limits: abstract_snippet_chars, max_highlights, max_highlight_chars
  - retry_count, overflow_detected
  - parse_error_type (if any)
  - finish_reason (if available)
  - raw_len_chars + head/tail excerpts (never full raw by default)

---

## Determinism Requirements
- Sorting:
  - retrieval snapshot preserves provider order OR sort by `paper_id` (choose one; document it)
  - rerank sorts by `(-score, paper_id)`
- Time:
  - `run_started_at_utc` written once (e.g., `run/meta.json`) and reused for digest `generated_at_utc`
- Prompt:
  - stable, versioned prompt file (e.g., `prompts/arxiv_synthesis_v1.md`)
  - include `prompt_version` in diagnostics
- Compression:
  - deterministic truncation by chars (not model tokens), same bounds each run

---

## Token Safety Strategy (minimal, high ROI)

### A) Compression (always)
Create `CompressedPaper` per top-k item:
- `paper_id`
- `title` (max chars)
- `published` (ISO)
- `categories` (short list)
- `abstract_snippet` (max chars)

Defaults (tune later):
- `title_max_chars=180`
- `abstract_snippet_chars=800` (for k≈10 this is typically safe)
- `max_highlights=10`
- `max_highlight_chars=240`

### B) Guardrail Estimator (heuristic)
Estimate prompt tokens from chars (no extra deps):
- `est_tokens = ceil(prompt_chars / 4)`

Budgets:
- `max_input_tokens_est` (e.g., 6000)
- `reserved_output_tokens` (e.g., 1200)
- `safety_margin_tokens` (e.g., 400)

If `est_tokens > (max_input_tokens_est - reserved_output_tokens - safety_margin_tokens)`:
- **truncate more aggressively** (reduce `abstract_snippet_chars` first, then reduce `max_highlights`, then reduce k)
- Only if still over budget at k<=10: enable chunking (rare path).

### C) Chunking (rare path; off by default)
Only if needed after aggressive truncation:
- chunk compressed papers into fixed-size groups (e.g., 5)
- synthesize highlights per chunk with same schema
- merge deterministically:
  - concat lists in chunk order
  - dedupe ONLY by `(paper_ids tuple, text)` exact match
  - enforce `max_highlights` with stable order

---

## Overflow / Truncation Recovery (simple)
Trigger recovery on:
- JSON parse failure OR schema validation failure
- AND (finish_reason == "length" OR raw output appears truncated)

Policy:
1) Retry once with stricter caps:
   - reduce `max_highlights` (e.g., 10 → 6)
   - reduce `max_highlight_chars` (e.g., 240 → 180)
2) If still failing:
   - reduce `abstract_snippet_chars` (e.g., 800 → 400)
   - (optional) reduce k (e.g., 10 → 7)
3) If still failing:
   - terminal failure with concise error + diagnostics artifact path

No silent fallback.

---

## Suggested Task List (Minimal Implementation Order)

### T0 — Repro + Diagnostics (baseline)
- [ ] Add fixture: `tests/fixtures/arxiv/papers_200.json` (or a recorded `papers_raw.json`)
- [ ] Add failure reproduction test for previous one-shot digest schema (expected to fail) to prove improvement.
- [ ] Add `synthesis_diagnostics.json` emission (even before new synthesis).

Acceptance:
- deterministic repro and diagnostics emitted on failure.

### T1 — Synthesis contract split (highest ROI)
- [ ] Add `SynthesisHighlights` schema.
- [ ] Update provider call to request `SynthesisHighlights` only.
- [ ] Build final `ResearchDigest` in Python:
  - papers copied from `papers_topk.json`
  - generated_at_utc from `run_started_at_utc`
  - highlights from LLM output

Acceptance:
- `digest.json` unchanged shape; truncation rate drops significantly.

### T2 — Input compression (high ROI)
- [ ] Implement `compress_papers(papers_topk, limits) -> compressed_papers`.
- [ ] Update prompt to use compressed payload only.
- [ ] Unit tests:
  - deterministic output
  - bounds enforced
  - stable ordering

Acceptance:
- prompt size reduced; stable output across runs.

### T3 — Budget guardrail (minimal)
- [ ] Implement `estimate_tokens_from_chars(text)`.
- [ ] Implement `apply_budget_limits(k, snippet_chars, max_highlights, ...)` deterministic reducer.
- [ ] Add metrics/diagnostics fields: prompt_chars, est_prompt_tokens, applied_limits.

Acceptance:
- synthesis never sends doomed prompts; guardrail triggers predictable truncations.

### T4 — Overflow recovery (safety net)
- [ ] Implement retry-on-parse-failure policy (1 retry).
- [ ] Add truncated-output detection heuristic (missing closing brace, etc.).
- [ ] Emit explicit `overflow_detected`, `retry_count`, `final_action`.

Acceptance:
- forced truncation test results in success or clean terminal failure with actionable diagnostics.

### T5 — Reranker top-k (if not already present)
- [ ] Implement deterministic weighted scorer + tie-breaks.
- [ ] Add per-research-area config:
  - category priors
  - recency weight
  - keyword lists
- [ ] Emit `rerank_scores.json` + `papers_topk.json`.

Acceptance:
- reranker stable; produces consistent top-k across replay.

---

## Config Surface (minimal defaults, per research area)

Under `metadata.config`:
- `retrieve.max_results`: 200
- `rerank.k`: 10
- `rerank.weights`: {category: ..., recency: ..., keyword: ...}
- `synthesis.max_highlights`: 10
- `synthesis.max_highlight_chars`: 240
- `synthesis.abstract_snippet_chars`: 800
- `synthesis.max_input_tokens_est`: 6000
- `synthesis.reserved_output_tokens`: 1200
- `synthesis.safety_margin_tokens`: 400
- `synthesis.overflow_retry_limit`: 1

Optional (keep off initially):
- `synthesis.chunking_enabled`: false
- `synthesis.chunk_size`: 5

---

## Tests (Regression Gates)

### Unit
- [ ] compressor determinism + bounds
- [ ] token estimator monotonicity
- [ ] budget reducer decisions deterministic
- [ ] merge/dedupe deterministic (exact-match only)

### Integration
- [ ] small path (<=5) single-call synthesis
- [ ] medium path (k=10) single-call synthesis
- [ ] forced truncation simulation triggers retry + emits diagnostics
- [ ] replay parity: identical `digest.json` bytes for same snapshot/config (including generated_at_utc sourced from run meta)

---

## Definition of Done
- [ ] Can retrieve 200 papers, rerank to k≈10, synthesize reliably without frequent truncation.
- [ ] `digest.json` unchanged downstream contract.
- [ ] Replay determinism: same snapshot/config => identical digest bytes.
- [ ] Diagnostics artifact always produced; failures are concise + actionable.
- [ ] No parallelization; no semantic dedupe; chunking disabled by default (rare path only).