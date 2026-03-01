## AgentForge ArXiv Scoring Plan (Retrieval Ranking + Topic Control)

## Purpose

Implement a deterministic, configurable scoring layer for ArXiv retrieval that:
- makes topic targeting explicit and controllable per plan
- ranks retrieved papers by multi-factor relevance/quality signals
- preserves replay determinism via snapshot artifacts
- remains compatible with the existing Control Plane / Execution Plane contracts

---

## Scope

In scope:
- scoring architecture for `arxiv.research`
- ranking configuration schema and validation
- scorer implementation with deterministic replay
- control-plan wiring and artifact outputs
- evaluation/test strategy

Out of scope (initial scorer rollout):
- web UI for ranking controls
- online learning/reinforcement tuning
- hard dependency on heavyweight ranking frameworks

---

## Success Criteria

1. Topic targeting is explicit in plan metadata (`metadata.config.query/categories/...`).
2. Ranking output is deterministic in replay mode for identical snapshots/config.
3. Ranking signals are auditable via manifest-indexed artifacts (score breakdowns).
4. End-to-end CLI workflows support ranked retrieval without breaking existing plans.
5. No hidden filesystem coupling; all handoff stays manifest-based.

---

## Ranking Objectives (V1)

Primary factors:
- topic_alignment
- citations
- credibility
- engagement
- recency
- methodological_rigor

Recommended V1 weighted score:
`final_score = Σ(weight_i * normalized_factor_i)` with user-overridable weights.

Constraints:
- all factor computations must be explainable and traceable
- no random tie-breaking (stable deterministic sort keys)
- if a factor is unavailable, apply explicit fallback policy (e.g., 0.0 + reason code)

---

## Determinism & Replay Rules

1. Live mode may call external services for scoring signals (if enabled by policy).
2. All external scoring signals MUST be written to snapshot artifacts.
3. Replay mode MUST consume only snapshots + config; no network access.
4. Score ordering in replay must be byte-for-byte stable for identical inputs.
5. Tie-break order must be deterministic (e.g., score desc, published desc, paper_id asc).

---

## Proposed Artifacts

Produced by ranking step/operation:
- `papers_ranked` (`outputs/papers_ranked.json`)
  - ranked list with final score and score breakdown
- `ranking_signals_snapshot` (`outputs/ranking_signals.json`) (optional in pure local mode)
  - raw external signals per paper (citations, metadata, etc.)
- `ranking_report` (`outputs/ranking_report.json`)
  - config, weights, factor stats, fallback counts, top-k diagnostics

Existing downstream:
- synthesis can consume `papers_ranked` (preferred) or fallback to `papers_raw`

---

## Proposed Data Model Additions

Add/extend models in `agents/arxiv_research/models.py`:

1) `RankingWeights`
- fields: topic_alignment, citations, credibility, engagement, recency, methodological_rigor
- validation: non-negative, sum > 0 (normalize internally)

2) `RankingConfig`
- fields:
  - `enabled: bool`
  - `strategy: "weighted_v1" | "hybrid_v1"`
  - `top_k: int | None`
  - `weights: RankingWeights`
  - `signal_sources: list[str]` (e.g., `["local", "semantic_scholar"]`)
  - `mode: "live" | "replay"` (inherits from request config if omitted)

3) `PaperScoreBreakdown`
- per-factor normalized scores
- final_score
- missing_signals/fallback_reasons

4) `RankedPaper`
- existing paper payload + `score: PaperScoreBreakdown`

---

## Execution Design Options

### Option A (Recommended): Dedicated rank operation/node

Add new plugin operation:
- `rank_retrieval`
  - input: `papers_raw` (+ optional signal snapshot in replay)
  - outputs: `papers_ranked`, `ranking_report`, `ranking_signals_snapshot?`

Plan shape:
- fetch_and_snapshot -> rank_retrieval -> synthesize_digest -> render_report

Pros:
- explicit artifact boundary
- easier testing/evaluation
- no hidden behavior inside fetch

### Option B: Ranking inside fetch step

Add ranking logic directly to `fetch_and_snapshot`.

Pros:
- fewer nodes

Cons:
- weaker separability and testability
- less flexible for future ranker variants

---

## Phase Plan

### Phase S0 — Contracts & Config Wire-up
- [ ] S0.1 Add `RankingConfig` and score models to `models.py`.
- [ ] S0.2 Validate config in ingest/ranker context parsing.
- [ ] S0.3 Update example plans with explicit ranking config blocks.

Acceptance:
- invalid ranking config fails fast with clear errors
- plans validate through existing `ControlPlan` tests

---

### Phase S1 — Deterministic Local Scorer (No External APIs)
- [ ] S1.1 Implement local factor extractors:
  - topic alignment (query/category/title/abstract lexical similarity)
  - recency
  - methodological rigor heuristics
- [ ] S1.2 Implement weighted aggregation + deterministic sorting.
- [ ] S1.3 Emit `papers_ranked` + `ranking_report`.

Acceptance:
- deterministic output for repeated runs over same snapshot/config
- score explanations present per paper

---

### Phase S2 — External Signal Adapter (Optional Live, Required Snapshot)
- [ ] S2.1 Add optional signal provider adapter (e.g., citations/engagement).
- [ ] S2.2 Enforce operations policy + allowlist for any network calls.
- [ ] S2.3 Snapshot external signals to artifact for replay parity.

Acceptance:
- replay works with snapshots and network disabled
- missing signal behavior is explicit and tested

---

### Phase S3 — Control-Plane Integration
- [ ] S3.1 Add `rank_retrieval` operation to `agents/arxiv_research/agent.yaml`.
- [ ] S3.2 Implement entrypoint routing and required input validation.
- [ ] S3.3 Ensure manifest artifact names remain unique and deterministic.

Acceptance:
- control runtime executes ranking node in plan sequence
- no duplicate artifact registration

---

### Phase S4 — Synthesis Integration
- [ ] S4.1 Prefer `papers_ranked` input in synthesis when present.
- [ ] S4.2 Keep backward compatibility with `papers_raw`.
- [ ] S4.3 Surface top-ranked rationale in digest metadata/report (optional).

Acceptance:
- existing plans still run
- ranked plans influence synthesis inputs deterministically

---

### Phase S5 — Evaluation & Regression Suite
- [ ] S5.1 Unit tests for each factor extractor and normalization.
- [ ] S5.2 Unit tests for weighted aggregation and tie-break determinism.
- [ ] S5.3 Replay parity tests (`live snapshot -> replay` identical ranking).
- [ ] S5.4 CLI integration tests for ranked dispatch/status/resume.

Acceptance:
- `python -m pytest` passes
- ranking regressions are caught by fixtures

---

### Phase S6 — Relevance Quality Benchmarks
- [ ] S6.1 Define labeled mini-benchmark for three domains:
  - LLM theory
  - LLM agents
  - LLM evaluation
- [ ] S6.2 Add offline metrics:
  - nDCG@k
  - Recall@k
  - Precision@k
- [ ] S6.3 Track score drift across config changes.

Acceptance:
- benchmark reports can compare scorer versions
- config changes are measurable and reproducible

---

## Initial Topic Plans (already aligned with this roadmap)

- `examples/arxiv_llm_theory_plan.yaml`
- `examples/arxiv_llm_agents_plan.yaml`
- `examples/arxiv_llm_evaluation_plan.yaml`

These define explicit `metadata.config` topic controls and ranking preferences.

---

## Suggested Repository Touchpoints

Core implementation:
- `agents/arxiv_research/models.py`
- `agents/arxiv_research/ingest.py` (or new `ranking.py`)
- `agents/arxiv_research/entrypoint.py`
- `agents/arxiv_research/agent.yaml`
- `examples/*.yaml` ranked plans

Tests:
- `agents/arxiv_research/tests/test_ingest.py`
- `agents/arxiv_research/tests/test_entrypoint.py`
- `agents/arxiv_research/tests/test_integration_replay.py`
- `agentforge/tests/orchestrator/test_cli_phase11_integration.py` (or scorer-specific integration file)

---

## Implementation Notes (Pragmatic)

- Prefer small pure functions for each factor and aggregation.
- Keep score math explicit and logged in artifacts.
- Avoid broad try/except; fail with typed, actionable errors.
- Keep external signal fetchers behind adapter interfaces.
- Do not alter Control Plane contracts; scorer is an agent-level capability.

---

## Definition of Done

- [ ] Ranked retrieval is available through plan-configurable settings.
- [ ] Replay mode produces identical ranked outputs from snapshots.
- [ ] Ranking report artifact explains why papers are ordered.
- [ ] End-to-end dispatch/status/resume tests pass for ranked plans.
- [ ] Full test suite passes with no regression in existing workflows.
