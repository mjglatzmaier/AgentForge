# Next Steps Plan

## 1) Goal(s)

- Run a reliable cron-based morning brief pipeline that summarizes relevant new papers.
- Expand from metadata-level summarization to paper-level learning artifacts (notes per selected paper).
- Preserve AgentForge determinism and replay behavior by keeping all intermediate outputs as manifest-indexed artifacts.

## 2) Potential Next Steps and Example Workflows

### A. Near-term (High ROI, low-medium effort)
- Increase retrieval recall and tighten selection:
  - Fetch larger candidate set (e.g., `max_results: 100-300`).
  - Score candidates with current scorer.
  - Select `select_m` (e.g., 50) then `top_k` (e.g., 5-10) for synthesis.
- Expose synthesis knobs in plan YAML:
  - `max_highlights`, `max_output_tokens`, `max_input_tokens_est`, `reserved_output_tokens`.

**Example workflow (morning brief v1.1):**
1. `fetch_and_snapshot` (live).
2. `score_papers` (large candidate pool -> top-k selected).
3. `synthesize_digest` (selected papers only, budget-safe).
4. `render_report` (brief markdown + source list).

### B. Paper-reading expansion (Medium effort)
- Add PDF + note generation chain after `score_papers`:
  1. `snapshot_pdfs` (download selected PDFs as snapshot artifacts).
  2. `extract_pdf_text` (extract normalized text by page/chunk).
  3. `paper_notes` (LLM per paper: summary, methods, caveats, action items).
  4. Optional `notes_aggregate` (cross-paper insights / reading queue).

**Example workflow (learning mode):**
1. Morning brief pipeline runs as above.
2. For selected papers, PDFs are snapshotted and parsed.
3. Per-paper notes are generated and linked from final report.
4. Notes become reusable artifacts for downstream agents (e.g., quiz/flashcards).

## 3) Architecture

- Keep each new capability as a dedicated step/node; avoid overloading `synthesize_digest`.
- Preserve artifact boundaries:
  - `papers_selected` -> `pdf_snapshots` -> `pdf_text_chunks` -> `paper_notes`.
- Keep deterministic replay:
  - Persist fetched PDFs and extracted text as artifacts.
  - In replay mode, read snapshots only (no network calls).
- Enforce manifest-only communication:
  - No hardcoded cross-step paths; always resolve via input artifacts.

## 4) Development Steps

1. **Config + contracts**
   - Define new artifact names and minimal schemas for PDF/text/notes.
   - Add plan YAML examples for “brief-only” and “learning mode.”

2. **Implement `snapshot_pdfs`**
   - Input: `papers_selected`.
   - Output: `pdf_snapshot_manifest` (and/or per-paper PDF artifacts).
   - Include retry + timeout + diagnostics fields.

3. **Implement `extract_pdf_text`**
   - Input: PDF snapshots.
   - Output: normalized text chunks + extraction diagnostics.
   - Add configurable limits (`max_pages`, `chunk_chars`).

4. **Implement `paper_notes`**
   - Input: text chunks + paper metadata.
   - Output: structured note artifact per paper + optional aggregate notes.
   - Keep JSON schema strict; render markdown as a downstream formatting step.

5. **Integrate report linking**
   - Update render step to link digest bullets to paper notes/PDF references.

6. **Testing + hardening**
   - Unit tests for each new step.
   - Replay integration tests with snapshot fixtures.
   - CLI smoke test for cron-like run with conservative token caps.

## 5) External Dependencies or Tools (if any)

- **Optional (recommended for PDF parsing):**
  - `pypdf` (lighter, text-first parsing).
  - `pymupdf` (better layout handling, typically faster).
- **Optional (if scanned PDFs become important):**
  - OCR stack (e.g., Tesseract) — defer unless needed due to complexity.
- **Scheduler/runtime:**
  - Existing cron + `agentforge dispatch` is sufficient for first production rollout.
- **No heavy orchestration frameworks needed** (keep current AgentForge architecture).
