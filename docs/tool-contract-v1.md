# tool-contract.md (v1): ToolSpec + Tool Calls + Capabilities

## Principles
- Agents do not execute arbitrary shell by default.
- Agents may request tool operations via the kernel (agentd).
- Kernel enforces capabilities + approval gates before dispatching calls.
- Tools are user-space services (separate processes) that expose versioned operations.

---

## Capability Model
Capabilities are strings in a controlled namespace.

Examples:
- `gmail.read.metadata`
- `gmail.read.body`
- `gmail.send`
- `exchange.read`
- `exchange.place_order`
- `net.fetch:https://news.example.com/*`
- `fs.read:runs/*`

Capabilities are granted per agent identity via policy.

---

## ToolSpec (manifest)
Each tool service provides a ToolSpec that declares its operations and requirements.

### ToolSpec JSON (example)
```json
{
  "tool_name": "gmaild",
  "tool_version": "1.0.0",
  "ops": [
    {
      "op_id": "gmail.list_messages",
      "input_schema": "GmailListMessagesIn",
      "output_schema": "GmailListMessagesOut",
      "required_capabilities": ["gmail.read.metadata"],
      "approval_required": false
    },
    {
      "op_id": "gmail.get_message_body",
      "input_schema": "GmailGetMessageBodyIn",
      "output_schema": "GmailGetMessageBodyOut",
      "required_capabilities": ["gmail.read.body"],
      "approval_required": true
    },
    {
      "op_id": "gmail.send_draft",
      "input_schema": "GmailSendDraftIn",
      "output_schema": "GmailSendDraftOut",
      "required_capabilities": ["gmail.send"],
      "approval_required": true
    }
  ]
}

Notes:

input_schema / output_schema are schema IDs that map to Pydantic models in code.

approval_required indicates the kernel must request explicit approval before dispatch.

Tool Call Envelope (kernel → tool service)

Kernel dispatches a tool call to a tool service with a standard envelope.

ToolCallRequest

{
  "request_id": "req_01HZY...",
  "run_id": "run_2026-03-04_...",
  "agent_id": "crypto.swing.v2",
  "op_id": "gmail.list_messages",
  "args": { "query": "is:unread", "max_results": 20 },
  "policy_snapshot_id": "pol_...",
  "issued_at": "2026-03-04T20:15:00Z"
}

ToolCallResponse

{
  "request_id": "req_01HZY...",
  "ok": true,
  "result": { "messages": [ { "id": "18c...", "from": "x@y.com", "subject": "...", "snippet": "..." } ] },
  "error": null,
  "completed_at": "2026-03-04T20:15:01Z"
}

If ok=false, return:

{
  "request_id": "req_...",
  "ok": false,
  "result": null,
  "error": { "code": "GMAIL_AUTH_REQUIRED", "message": "OAuth token missing/expired" },
  "completed_at": "..."
}

Approval Protocol (kernel internal)

If an op is approval-required, kernel emits an approval event before dispatch.

ApprovalRequested event payload (example)

{
  "approval_id": "appr_01HZ...",
  "run_id": "run_...",
  "agent_id": "gmail.triage",
  "op_id": "gmail.send_draft",
  "summary": "Send draft to boss@company.com subject='Re: Update'",
  "requested_at": "2026-03-04T20:20:00Z"
}

Kernel will only dispatch the tool call after explicit approve.

Redaction Rules (recommended)

Tool responses may include sensitive content; kernel should support per-op redaction.

Default:

store full content as an artifact file with restricted permissions

store only hashes/metadata in event log

Approval UI shows summarized, non-sensitive previews.

Service Transport

v1 recommended:

localhost HTTP (FastAPI) for each service (simple)

kernel calls services via allowlisted localhost endpoints

Later:

switch to gRPC for strict IDL + better C client ergonomics

Non-goals (v1)

perfect sandboxing (containers) — can be added later

distributed execution — local-first

