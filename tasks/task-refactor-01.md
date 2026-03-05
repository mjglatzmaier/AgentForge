# tasks.md: Microkernel Refactor Plan (AgentForge → AgentOS Control Plane)

## Goals (must remain front-and-center)
- Least-privilege tool access via capabilities
- Approval gates for irreversible actions (email send, trades)
- Append-only event log for audit + replay
- Cross-platform (macOS/Windows/Linux) using Python-first implementation
- Lumen as a Workbench client (visualize runs + approvals), no secrets in UI

---

## 0.0 Repo layout (suggested)
agentforge/
agentd/ # kernel control plane (python)
agentctl/ # CLI (python)
core/ # shared schemas + policy
services/
gmaild/ # Gmail connector service (python)
exchanged/ # Trading connector service (python)
rssd/ # Example fetcher connector (python)
arxiv/ # Example arxiv paper fetcher (could include alpharix, reddit, etc.)
lumen_client/ # API notes + C client helper (no secrets)
docs/
ADR-000X-microkernel.md
tool-contract.md
policy.md


---

## 0.1 Event Model v1 (append-only, audit-friendly)
- [X] Define event schema (JSON objects; append-only JSONL per run)
  - `RunStarted`, `StepStarted`, `ToolCallRequested`, `ApprovalRequested`,
    `ToolCallCompleted`, `ArtifactWritten`, `StepCompleted`,
    `RunCompleted`, `RunFailed`
- [X] Implement event writer:
  - write to `runs/<run_id>/events.jsonl`
  - optionally index metadata in SQLite for fast listing
- [X] Implement read APIs:
  - `GET /runs/{run_id}/events` (paged)
  - `WS /events/stream` (push live events)

**Deliverable:** run a toy pipeline and watch live events in CLI.

---

## 0.2 Tool Contract v1 (kernel-brokered tools)
- [X] Define `ToolSpec` manifest:
  - `name`, `version`
  - operations: `op_id`, input/output schema, required capabilities, `approval_required`
- [X] Implement Tool Broker in `agentd`:
  - validate tool call inputs/outputs (Pydantic)
  - enforce capabilities
  - enforce timeouts/retries
  - log tool call request/response into event log

**Deliverable:** kernel can call a separate “hello tool service” and record full trace.

---

## 0.3 Policy Engine v1 (caps + approvals + limits)
- [X] Define `AgentIdentity`:
  - `agent_id`, `role`, allowed capabilities
- [X] Define policy config file (YAML or JSON):
  - allowed caps per agent
  - approval rules per tool op
  - rate limits (per tool/agent)
  - domain allowlists (for any net fetch tool)
- [X] Enforce policy inside kernel before tool call dispatch

**Deliverable:** same agent behaves differently under different policy snapshots.

---

## 0.4 Approval Flow v1 (hard gates)
- [X] Kernel emits `ApprovalRequested` with stable `approval_id`
- [X] API endpoints:
  - `GET /approvals` (pending)
  - `POST /approvals/{approval_id}:approve`
  - `POST /approvals/{approval_id}:deny`
- [X] CLI UX:
  - `agentctl approvals list`
  - `agentctl approve <id>` / `deny <id>`

**Deliverable:** “send email” and “place order” cannot occur without explicit approval.

---

## 0.5 Gmail connector service (gmaild) — safe-by-default
- [X] `agentctl auth gmail` (or `gmaild auth`) does OAuth and stores tokens in OS keychain (`keyring`)
- [X] Tool ops:
  - `list_messages(query, max)` → metadata+snippet only
  - `get_message_metadata(message_id)` → headers only
  - `get_message_body(message_id)` → body (approval-required)
  - `create_draft(to, subject, body)` → draft_id (approval-required optional)
  - `send_draft(draft_id)` → message_id (approval-required)
- [X] Default behavior:
  - metadata-first, body on-demand
  - never auto-send

**Deliverable:** inbox triage pipeline generates summaries + drafts, asks before sending.

---

## 0.6 Trading connector service (exchanged) — risk-limited execution
- [ ] Store API keys in OS keychain
- [ ] Tool ops:
  - `get_balances`
  - `get_positions`
  - `place_order` (approval-required)
- [ ] Hard risk controls inside connector:
  - max notional per order
  - allowlisted symbols
  - max orders per day
  - optional daily max loss guard (basic)

**Deliverable:** crypto swing agent proposes trades; execution is gated + bounded.

---

## 0.7 Cross-platform packaging and dev workflow
- [ ] `agentctl up` starts:
  - `agentd`
  - enabled connector services
- [ ] `agentctl down` stops them
- [ ] Localhost-only listening by default
- [ ] Add `.env.example` for ports + paths

**Deliverable:** works on macOS/Windows/Linux without OS-specific service install.

---

## 0.8 Lumen Workbench integration (minimal)
- [ ] Lumen connects to `agentd`:
  - list runs
  - stream events
  - list approvals + approve/deny
  - browse artifacts
- [ ] UI:
  - Runs list panel
  - Event timeline panel
  - Approval modal
  - Artifact viewer (open from run dir)

**Deliverable:** Lumen can visualize runs and safely approve gated actions.

---

## Guardrails (MUST)
- No raw secrets in agent prompts
- No arbitrary shell tool by default
- All irreversible actions require approval in v1
- Every tool call is logged (inputs/outputs redacted as needed)
