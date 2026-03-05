# lumen-integration-v1.md: Workbench Client Contract

## Principle

Lumen is a **Workbench client** for visibility and operator control.  
Lumen does **not** execute tools, run connectors, or hold secrets.

---

## Current Integration Strategy

- Treat Lumen as a harvested-reference input only; no in-repo runtime submodule dependency.
- Harvest only reusable UX/runtime patterns (timeline, approvals, artifact browsing, scheduling visuals).
- Do not couple AgentForge kernel APIs to game-engine internals.
- Keep workbench protocol stable so Lumen can be swapped with another client implementation if needed.

---

## v1 Responsibilities

Lumen may:
- render runs, graph/timeline, and artifacts,
- show pending approvals and submit human decisions,
- send high-level run control actions (`pause`, `resume`, `cancel`) via kernel APIs.

Lumen may not:
- bypass policy/approval gates,
- call connector operations directly,
- access credential material.

---

## Required `agentd` API Surface (v1)

### Runs
- `GET /runs` — list runs
- `GET /runs/{run_id}` — run summary/details
- `GET /runs/{run_id}/graph` — node graph and states

### Events
- `GET /runs/{run_id}/events?after=<cursor>` — paged event stream
- `GET /runs/{run_id}/timeline` — normalized timeline projection
- `WS /events/stream` — live events (optionally filtered by run/agent)

### Approvals
- `GET /approvals` — pending approvals
- `POST /approvals/{approval_id}:approve`
- `POST /approvals/{approval_id}:deny`

### Run Control
- `POST /runs/{run_id}:pause`
- `POST /runs/{run_id}:resume`
- `POST /runs/{run_id}:cancel`

### Artifacts
- `GET /runs/{run_id}/artifacts` — artifact index
- `GET /runs/{run_id}/artifacts/{artifact_id}` — metadata and safe preview/open metadata

---

## Event Contract Requirements

Events consumed by Lumen should include:
- `event_id`
- `timestamp_utc`
- `run_id`, `node_id`, `agent_id`
- `event_type` (scheduler transition, tool lifecycle, approval lifecycle)
- `summary` (human-readable)
- `payload` (typed detail)

Lumen should treat events as append-only and cursor-based.

---

## Security & Trust Boundary

- Lumen connects only to local/trusted `agentd` endpoint.
- All mutation endpoints require authenticated operator session.
- Approval actions require CSRF-safe or signed request semantics.
- Artifact access is read-only and path-sandboxed to run directories.
- Secret fields are redacted by `agentd` before data reaches Lumen.

---

## Front-End Technology Recommendation

- Preferred UI stack for native workbench clients: **Dear ImGui**.
- Recommended architecture:
  - AgentForge side-car remains Python-first (`agentd` + contracts + policy + approvals).
  - Native UI client (Lumen or replacement) consumes local `agentd` APIs over typed JSON contracts.
  - Render-layer decisions (Vulkan/OpenGL/Metal) remain entirely in the workbench client boundary.
- This preserves developer velocity in kernel/core while allowing high-performance native UX.

---

## Cross-Platform Integration Notes

- Transport should support localhost TCP and OS-native IPC wrappers.
- File-open behavior for artifact previews must use platform adapters.
- UI must degrade gracefully when optional event streaming is unavailable (poll fallback).

---

## Future Extensions (non-v1)

- interactive replay mode,
- scenario diff view across runs,
- policy simulation panel,
- scheduler heatmaps and queue health telemetry.
