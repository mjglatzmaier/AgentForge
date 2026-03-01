# Research Reader Tasks

## 1. Goals

- Provide a private, single-user research reading workspace for papers discovered via AgentForge (or manual import).
- Offer a high-quality PDF reading experience with an adjacent collapsible AI chat pane.
- Enable rapid understanding workflows: summaries, Q&A, note capture, citations, and reusable learning artifacts.
- Make past papers and artifacts easy to find, filter, and reopen (strong personal knowledge continuity).
- Support one-click export of session outputs to a vector DB for downstream retrieval by your other agents.

## 2. Architecture Overview

### Core Components
- **Reader UI**
  - PDF viewer (page nav, zoom, search, highlight hooks)
  - Collapsible chat panel
  - Notes/artifacts side panel
  - Library/search view for past papers and sessions
- **Application API**
  - Session lifecycle (start, continue, export, archive)
  - Chat orchestration (selected model, context window management, citation anchors)
  - Artifact persistence (notes, summaries, Q&A logs, chunk references)
- **Storage Layer**
  - Paper DB (metadata, tags, status, source run linkage)
  - Session DB (messages, prompts, notes, exports, timestamps)
  - Artifact store (JSON/markdown snapshots, optional local file attachments)
- **Retrieval/Export Layer**
  - Embedding pipeline for approved artifacts/chunks
  - Vector DB export (namespace per user/project/session)
  - Traceability back to original paper/session artifacts

### Data Flow (Typical)
1. Import selected paper(s) + optional PDF/text artifacts.
2. Open Reader Session with model selection.
3. Read PDF + ask questions + capture notes.
4. Save session outputs as structured artifacts.
5. Export chosen artifacts/chunks to vector DB.

## 3. Scope

### In Scope (MVP)
- Single-user local/private app.
- PDF reader + chat + notes.
- Library page with strong search/filter/sort:
  - by title, author, tags, topic, date, run_id/session_id.
- Session persistence with resumable conversations.
- Export selected notes/chunks/summaries to vector DB.

### Out of Scope (MVP)
- Multi-user auth/roles.
- Real-time collaboration.
- Enterprise-grade admin/ops controls.
- Complex OCR-heavy scanned document pipeline (unless needed immediately).

## 4. Open Source Tools

- **PDF UI**
  - PDF.js (via React PDF wrappers) for robust browser rendering.
- **LLM app references (for ideas/components)**
  - Open WebUI
  - AnythingLLM
  - LibreChat
- **PDF/text extraction**
  - PyMuPDF (fitz) or pypdf for extraction pipeline needs.
- **Vector stores**
  - Qdrant, Weaviate, or pgvector (Postgres extension).
- **Optional parsing upgrades**
  - Unstructured / LlamaParse (if extraction quality becomes bottleneck).

## 5. Recommended Tech Stack

### Frontend
- Next.js + React + TypeScript
- PDF.js viewer integration
- Tailwind (or component library) for fast, clean UX

### Backend
- FastAPI (Python) for API and model orchestration
- Background task runner (lightweight queue or async workers) for ingestion/embedding jobs

### Storage
- SQLite for MVP (single-user), upgradeable to Postgres later
- Local object/file store for raw artifacts and exports

### Vector
- Qdrant (simple local Docker/self-host) or pgvector (if you want one DB stack)

### AI Layer
- Provider-agnostic client abstraction (compatible with your AgentForge direction)
- Structured outputs for notes/summaries/citation traces

## 6. Development Steps

1. **Define contracts**
   - Session schema, paper schema, artifact schema, export schema.
2. **Build library/discovery UI**
   - Fast search/filter for past papers/artifacts.
3. **Implement Reader Session**
   - PDF panel + collapsible chat + notes capture.
4. **Context handling**
   - Chunking and retrieval of relevant paper text per question.
5. **Artifact persistence**
   - Save all chat turns, notes, citations, and summary artifacts.
6. **Export pipeline**
   - Embed selected artifacts/chunks and push to vector DB namespace.
7. **Integrate with AgentForge outputs**
   - Import path for `papers_selected`, digest/report artifacts, and run linkage metadata.
8. **Hardening**
   - Add replay-like deterministic traces where practical, and tests for ingestion/session/export flows.

## 7. Repo Name + Other Requirements to Include

### Suggested Repo Names
- `research-reader`
- `paper-reader-studio`
- `agentforge-reader`

### Requirements to Explicitly Capture Early
- **Privacy mode defaults** (local-only by default, explicit opt-in for remote providers).
- **Data retention policy** (how long to keep session logs/artifacts).
- **Citation trace UX** (click note -> jump to source page/chunk).
- **Session portability** (import/export session bundle JSON).
- **Model switching policy** (per session vs per message).
- **Failure transparency** (clear diagnostics for parse/extract/model/export failures).
- **Cron interoperability** (simple import from morning brief outputs).
