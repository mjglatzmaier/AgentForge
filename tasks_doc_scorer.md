# steps_paperscorer.md
# AgentForge: Paper Scorer Step (arxiv.research.score_papers) — Funnel Scoring + Deterministic Ranking

## Purpose
Add a deterministic, configurable **paper scoring + selection** step that turns a high-recall retrieval set (e.g., up to **200**) into a smaller candidate pool (**M**, e.g., 40–60) and then optionally to **top-k** (e.g., 10) for synthesis.

This is the “funnel” stage that makes the system useful by:
1) improving **alignment to your interests**
2) improving **quality**
3) ordering by **engagement/impact** so the “known / high-signal” papers rise first

This step must preserve replay determinism and produce auditable artifacts.

---

## Where it fits in the pipeline
Recommended node sequence:

1) `fetch_and_snapshot`  → `papers_raw` (N up to 200)
2) **`score_papers`**     → `papers_scored`, `papers_selected` (M)
3) `rerank_papers` (optional, heavier) → `papers_topk` (k≈10)
4) `synthesize_digest`    → `digest_json`
5) `render_report`        → `report_md`

If you want to keep your current pipeline minimal, you can start with **score_papers only** and have synthesis take the top-k from its output.

---

## Step Contract
**Operation:** `arxiv.research.score_papers`  
**Inputs:** `papers_raw`  
**Outputs:**
- `outputs/papers_scored.json` (all N with per-factor breakdown)
- `outputs/papers_selected.json` (top M after scoring, stable-ordered)
- `outputs/scoring_diagnostics.json` (config + summary stats)

---

## Determinism Requirements
- Do not use random numbers.
- All tie-breakers must be stable and explicit:
  - primary: total score (descending)
  - secondary: published timestamp (descending)
  - tertiary: `paper_id` (ascending lexical)
- Normalize text deterministically (lowercase, strip, collapse whitespace).
- Any “now time” must come from run metadata (e.g., `run_started_at_utc`) so replay is stable.

---

## Input Assumptions (papers_raw schema)
Each paper in `papers_raw` should include at least:
- `paper_id` (e.g., arXiv id)
- `title`
- `abstract` (or summary)
- `categories` (list[str], primary + secondary if available)
- `published` (ISO8601)
Optional (if available from your fetch stage):
- `authors` (list[str])
- `comment` / `journal_ref`
- `doi`
- `links` (pdf/html)

**Important:** arXiv alone does not reliably provide “citations” or “engagement” metrics.  
So the scorer supports:
- **local-only proxies** (fast, no web)
- **optional enrichment fields** if your fetch stage adds them later (e.g., citations count from Semantic Scholar/OpenAlex)

This lets you ship v1 without external dependencies.

---

## Scoring Model (Funnel)
### Overall Score
`score_total = Σ_i weight_i * feature_i(paper)`

Where each `feature_i` is normalized to [0, 1] (or [-1, 1] if penalizing), and weights sum to 1.0 by default.

### Factors (v1 recommended)
#### 1) Topic Alignment (high ROI; required)
Measures whether the paper matches your plan query and interests.

**Signals (deterministic, local):**
- keyword hits in title (higher weight than abstract)
- keyword hits in abstract snippet
- category match bonus (if category in plan categories)
- phrase match bonus (exact phrases like “scaling laws”, “parameter-efficient tuning”)

**Implementation detail:**
- Use a plan-provided **keyword set** + **phrase set**.
- Count matches with simple substring or token-based match (no embeddings required for v1).

#### 2) Recency (high ROI; required)
Prefers newer papers when you’re learning fast-moving areas.

Example mapping:
- `age_days = (run_started_at_utc - published)`
- `feature_recency = exp(-age_days / half_life_days)`  
Defaults:
- `half_life_days = 180` for fast fields (LLM methods), or configurable per plan.

#### 3) Credibility / Venue Proxy (medium ROI; optional)
arXiv itself doesn’t guarantee peer review, but you can use proxies:
- presence of `journal_ref` or `doi` → small boost
- presence of “accepted at”, “published in”, etc. in comments → small boost
- penalize “work in progress” / “draft” flags if you want

Keep this gentle; don’t overfit.

#### 4) Methodological Rigor Proxy (medium ROI; optional)
Local heuristic signals:
- mentions of “experiments”, “ablation”, “benchmark”, “evaluation”
- presence of “theorem/proof” terms if theory-focused
- penalize overly vague abstracts (very short / marketing-y)

This is a proxy; keep weight moderate.

#### 5) Impact / Engagement (optional now; big ROI later)
**v1 (local-only proxies):**
- “survey”, “benchmark”, “scaling laws”, “foundation model”, “comprehensive” terms can correlate with higher community attention
- “code available”, “github”, “released code” in abstract/comment → boost
- multi-institution / well-known labs list (only if you maintain a curated allowlist—optional)

**v2 (true metrics via enrichment):**
If `papers_raw` includes `citations_count`, `influential_citations`, `tweet_count`, `github_stars`, etc:
- `feature_citations = log1p(citations_count) normalized`
- `feature_engagement = log1p(tweet_count + github_stars + …) normalized`

**Design rule:** treat enriched fields as optional inputs. If absent, compute proxy feature; never fail.

---

## Output Artifacts

### outputs/papers_scored.json
List of N scored entries, stable-sorted by final ordering, each item:

```json
{
  "paper_id": "2501.01234",
  "title": "...",
  "published": "2026-02-20T12:00:00Z",
  "categories": ["cs.CL", "cs.LG"],
  "score_total": 0.8421,
  "scores": {
    "topic_alignment": 0.91,
    "recency": 0.77,
    "credibility": 0.35,
    "methodological_rigor": 0.62,
    "engagement": 0.58
  },
  "explanations": {
    "topic_alignment": ["title_hit: scaling laws", "abstract_hit: finetuning", "category_match: cs.CL"],
    "credibility": ["has_doi"],
    "engagement": ["mentions: code", "mentions: benchmark"]
  }
}
```

## outputs/papers_selected.json

List of M selected papers (full paper objects copied deterministically from papers_raw), ordered exactly as selected.

### outputs/scoring_diagnostics.json
```json
{
  "scorer_version": "paperscorer_v1",
  "run_started_at_utc": "...",
  "input_count": 200,
  "selected_count": 50,
  "config": { "...": "..." },
  "summary": {
    "avg_score_total": 0.44,
    "p95_score_total": 0.82,
    "top_categories": [["cs.CL", 37], ["cs.LG", 29]]
  }
}
```

# Config Surface (Plan YAML)

Add to metadata.config.scoring (or ranking if you prefer, but keep it distinct from retrieval sort):

```yaml
scoring:
  enabled: true
  select_m: 50              # funnel size after scoring (from N=200)
  min_score_threshold: 0.0  # optional gate
  tie_breakers: [score_total_desc, published_desc, paper_id_asc]

  topic_alignment:
    keywords:
      - "scaling laws"
      - "parameter-efficient tuning"
      - "finetuning"
      - "benchmark"
      - "transformer"
      - "LLM"
      - "physics"
    phrases:
      - "scaling laws"
      - "parameter-efficient tuning"
    title_weight: 2.0
    abstract_weight: 1.0
    category_bonus: 0.15

  recency:
    half_life_days: 180

  credibility:
    doi_bonus: 0.10
    journal_ref_bonus: 0.10

  methodological_rigor:
    experiment_terms: ["ablation", "evaluation", "benchmark", "experiments"]
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
```

# Recommended Node Addition (example)
Insert this between fetch_and_snapshot and synthesize_digest:
```yaml
- node_id: score_papers
  agent_id: arxiv.research
  operation: score_papers
  inputs: [papers_raw]
  outputs: [papers_scored, papers_selected, scoring_diagnostics]
  depends_on: [fetch_and_snapshot]
  metadata:
    config:
      mode: replay
      scoring:
        enabled: true
        select_m: 50
        # ... (as above)
```
Then change synthesis to use papers_selected (or papers_topk if you add a reranker):
```
- node_id: synthesize_digest
  agent_id: arxiv.research
  operation: synthesize_digest
  inputs: [papers_selected]
  outputs: [digest_json]
  depends_on: [score_papers]
```

# Evaluation / Tests (must-have)
## Unit
Determinism: same input + config ⇒ identical papers_scored.json bytes
Bounds: explanations list capped; no unbounded growth
Tie-break stability
## Integration
Fixture with 200 papers:
selected_count == M
stable ordering
synthesis succeeds without truncation using selected/top-k inputs

## Dependencies & Modes (Explicit)

### Default Mode (v1): Local-Only Deterministic Scoring (NO external models)
**Requires:** Python stdlib only (+ existing AgentForge deps like `pydantic` if already used elsewhere).  
**Does NOT require:** embeddings, transformers, torch, sentencepiece, numpy, sklearn, faiss, or any external API.

**Allowed deps (stdlib):**
- `re`, `math`, `datetime`, `collections`, `statistics`, `json`, `hashlib` (hashlib optional), `typing`

**Optional (already common in repo):**
- `pydantic` for schema validation (if AgentForge already uses it)
- `python-dateutil` (only if already in repo; otherwise implement ISO parsing via stdlib)

**How scoring works (local-only):**
- keyword/phrase hits in title + abstract snippet
- category overlap bonus
- recency via deterministic decay function
- lightweight proxies: presence of DOI/journal_ref/comment patterns; “code/github” mentions
- stable tie-break ordering

✅ This mode is the recommended default for initial rollout.

---

### Optional Mode (v2): Enrichment-based Scoring (External APIs, still deterministic via snapshot)
**Purpose:** Use real engagement/impact signals (citations, venue, etc.)

**Requires (explicit):**
- A new enrichment step (or fetch expansion) that writes `papers_enriched.json` to snapshot:
  - `citations_count`, `influential_citations`, `venue`, etc.
- HTTP client: `httpx` or `requests` (choose one; make it explicit)
- Provider(s): Semantic Scholar API and/or OpenAlex API (explicit endpoints + rate limits)

**Determinism rule:** Enrichment results must be written to an artifact and used in replay.  
No live re-query during replay.

**Note:** This mode should be a separate step:
- `arxiv.research.enrich_papers` (live) → `papers_enriched`
Then scorer consumes `papers_enriched` instead of `papers_raw`.

---

### Optional Mode (v3): Neural Reranking (External model libs; higher cost)
**Purpose:** Improve quality when heuristics aren’t enough.

**Requires (explicit):**
- Local model runtime choice (pick one):
  - **ONNX Runtime** (`onnxruntime`) + a chosen reranker model (packaged or downloaded)
  - or **Transformers** (`transformers`, `torch`) + a specific cross-encoder model
- A model management policy:
  - pinned model name + checksum
  - local cache path under a deterministic snapshot mechanism

**Recommendation:** Keep this as a separate node:
- `arxiv.research.rerank_papers` consumes M (e.g., 50) and outputs k (e.g., 10)
So you never run model inference on all 200.

---

## Step-by-Step Explicit Instructions for copilot-cli (v1 scorer)

### Step Name
`arxiv.research.score_papers` (local-only)

### Inputs
- `papers_raw` (JSON artifact with list of papers)

### Outputs
- `outputs/papers_scored.json`
- `outputs/papers_selected.json`
- `outputs/scoring_diagnostics.json`

### Explicit non-requirements
- MUST NOT call external web APIs
- MUST NOT require any new third-party ML libraries
- MUST NOT depend on embeddings or LLM calls

### If the repo uses Pydantic
- Define `PaperRaw`, `PaperScored`, `ScoringConfig` models.
Otherwise:
- Use plain dicts and validate required keys manually.

---

## Plan YAML: Make the mode explicit
Add:
```yaml
scoring:
  mode: local_v1  # options: local_v1 | enrich_v2 | neural_v3