## AgentForge V1 ArXiv Document Scorer Implementation Plan

## Purpose

Deliver a **production-usable v1 scorer** for `arxiv.research` that:
- ranks retrieval results deterministically
- selects a compact, high-signal paper set for synthesis
- remains easy to extract later into shared core utilities
- is fully covered by unit/integration tests inside `agents/arxiv_research`

---

## Why a v2 Task Doc (Assessment of `tasks_doc_scorer.md`)

`tasks_doc_scorer.md` is strong on factor ideas and heuristics, but needs tighter implementation specificity for smooth execution:
1. no explicit phased task IDs/checklist flow like refactor docs
2. no concrete file-level implementation map
3. no clear extraction boundary for future shared utility
4. no strict contract details for replay/offline vs optional enrichment
5. tests are listed, but not organized into actionable gates by phase

This document addresses those gaps with implementation-ready phases.

---

## Scope (V1)

In scope:
- new scorer operation for `arxiv.research` (`score_papers`)
- deterministic feature scoring + weighted aggregation
- `papers_selected` handoff to synthesis
- replay-safe operation (no network required)
- optional enrichment hooks (disabled by default)
- unit/integration tests

Out of scope:
- online learning
- UI configuration
- heavy ranking frameworks
- mandatory external APIs

---

## V1 Architecture (Extraction-Friendly)

Implement scorer with a clean internal boundary:

1) **Domain layer (pure, extraction-ready)**  
`agents/arxiv_research/scoring/`:
- `models.py` (typed scoring config/result models)
- `features.py` (pure feature extractors)
- `aggregate.py` (weight normalization + final score)
- `select.py` (deterministic ordering + select_m/top_k)

2) **Agent adapter layer (AgentForge-specific)**  
- `agents/arxiv_research/scoring_step.py` (ctx/artifact IO, calls domain layer)
- `agents/arxiv_research/entrypoint.py` operation routing

Extraction path later:
- move `scoring/` package to shared repo module with minimal API changes
- keep `scoring_step.py` agent-specific

---

## Step / Operation Contract (V1)

Operation: `score_papers`  
Input artifacts:
- `papers_raw` (required)

Output artifacts:
- `papers_scored` -> `outputs/papers_scored.json`
- `papers_selected` -> `outputs/papers_selected.json`
- `scoring_diagnostics` -> `outputs/scoring_diagnostics.json`

Contract rules:
- output paths must be `outputs/...`
- deterministic ordering:
  1) `score_total` desc
  2) `published` desc
  3) `paper_id` asc
- no randomization
- no network calls in replay mode

---

## Config Contract (`metadata.config.scoring`)

```yaml
scoring:
  enabled: true
  scorer_version: "v1"
  select_m: 40
  top_k: 10
  min_score_threshold: 0.0
  tie_breakers: [score_total_desc, published_desc, paper_id_asc]

  topic_alignment:
    keywords: ["llm", "scaling", "agent", "evaluation"]
    phrases: ["scaling laws", "tool use", "multi-turn evaluation"]
    title_weight: 2.0
    abstract_weight: 1.0
    category_bonus: 0.15

  recency:
    half_life_days: 180

  credibility:
    doi_bonus: 0.10
    journal_ref_bonus: 0.10

  methodological_rigor:
    experiment_terms: ["ablation", "benchmark", "evaluation", "experiments"]
    theory_terms: ["theorem", "proof", "lemma"]

  engagement:
    proxy_terms: ["code", "github", "benchmark", "survey", "dataset"]
    proxy_bonus_per_hit: 0.05
    max_proxy_bonus: 0.25

  weights:
    topic_alignment: 0.45
    recency: 0.20
    credibility: 0.10
    methodological_rigor: 0.15
    engagement: 0.10

  enrichment:
    enabled: false
    source: null
```

Validation:
- weights non-negative, sum > 0 (normalize internally)
- `select_m >= 1`, `top_k >= 1` when provided
- `top_k <= select_m` when both provided
- invalid config fails fast with explicit errors

---

## Data Model Additions (Agent Level)

Add models (agent-side):
- `ScoringConfig`
- `ScoringWeights`
- `PaperFeatureScores`
- `ScoredPaper`
- `ScoringDiagnostics`

Do not change global `agentforge/contracts/models.py` unless strictly needed.

---

## Phased Tasks

### Phase S1 — Contracts + Models
- [ ] S1.1 Add scorer models in `agents/arxiv_research/scoring/models.py`
- [ ] S1.2 Add config parser from `ctx["config"]["scoring"]` with defaults
- [ ] S1.3 Add unit tests for model validation and defaults

Acceptance:
- valid/invalid scoring config behavior is fully tested

---

### Phase S2 — Deterministic Feature Engine
- [ ] S2.1 Implement topic alignment feature
- [ ] S2.2 Implement recency feature
- [ ] S2.3 Implement credibility + rigor + engagement proxy features
- [ ] S2.4 Ensure normalized feature outputs and capped ranges

Acceptance:
- feature outputs deterministic and bounded
- explanation snippets available per factor

---

### Phase S3 — Aggregation + Selection
- [ ] S3.1 Implement weighted aggregation (`score_total`)
- [ ] S3.2 Implement deterministic tie-break ordering
- [ ] S3.3 Implement `select_m`, `top_k`, and threshold logic
- [ ] S3.4 Emit `papers_scored` + `papers_selected` + diagnostics payload

Acceptance:
- same input/config produces byte-stable scoring outputs

---

### Phase S4 — Step Integration (`score_papers`)
- [ ] S4.1 Add `scoring_step.py` using step-style ctx contract
- [ ] S4.2 Add `score_papers` route in `entrypoint.py`
- [ ] S4.3 Add operation metadata in `agents/arxiv_research/agent.yaml`
- [ ] S4.4 Validate required input artifact mapping (`papers_raw`)

Acceptance:
- control runtime can execute scorer operation end-to-end

---

### Phase S5 — Pipeline Wiring to Synthesis
- [ ] S5.1 Update example plan(s) to insert `score_papers` node
- [ ] S5.2 Update synthesis to prefer `papers_selected` input
- [ ] S5.3 Keep backward compatibility (`papers_raw` fallback)

Acceptance:
- ranked plans work without breaking existing non-ranked plans
- synthesis token pressure reduced via selected subset

---

### Phase S6 — Replay Determinism + Enrichment Hook
- [ ] S6.1 Implement optional enrichment adapter interface (disabled by default)
- [ ] S6.2 If enrichment used live, snapshot signals to artifact
- [ ] S6.3 In replay, consume only snapshots (no network)

Acceptance:
- replay parity verified with and without enrichment path

---

### Phase S7 — Test Matrix + Regression Gates
- [ ] S7.1 Unit tests (`agents/arxiv_research/tests/test_scoring_*.py`):
  - config validation
  - feature calculations
  - aggregation math
  - ordering stability
- [ ] S7.2 Entry-point tests:
  - operation routing
  - required input enforcement
  - output artifact contract
- [ ] S7.3 Integration tests:
  - replay fixture with larger candidate set
  - no duplicate manifest artifacts
  - deterministic output across repeated runs
- [ ] S7.4 CLI smoke tests:
  - dispatch/status/resume on scorer-enabled plan

Acceptance:
- `python -m pytest` passes
- scorer regressions are covered by deterministic fixtures

---

## Files to Implement / Update

New:
- `agents/arxiv_research/scoring/models.py`
- `agents/arxiv_research/scoring/features.py`
- `agents/arxiv_research/scoring/aggregate.py`
- `agents/arxiv_research/scoring/select.py`
- `agents/arxiv_research/scoring_step.py`
- `agents/arxiv_research/tests/test_scoring_models.py`
- `agents/arxiv_research/tests/test_scoring_features.py`
- `agents/arxiv_research/tests/test_scoring_step.py`

Update:
- `agents/arxiv_research/entrypoint.py`
- `agents/arxiv_research/agent.yaml`
- `agents/arxiv_research/synthesis.py`
- `examples/arxiv_llm_*.yaml` (or dedicated scorer example plan)

---

## Determinism & Quality Rules (Non-Negotiable)

1. Message = Artifact invariant preserved.
2. Replay mode must be network-free.
3. Stable deterministic sort and serialization.
4. Explicit fallback behavior when optional fields/signals absent.
5. No silent failures; errors must be clear and typed.

---

## Definition of Done

- [ ] `score_papers` operation implemented and routable.
- [ ] `papers_selected` drives synthesis in scorer-enabled plans.
- [ ] Deterministic replay for scorer outputs verified.
- [ ] Unit + integration tests added and passing.
- [ ] Implementation remains extractable to shared utility with minimal refactor.
