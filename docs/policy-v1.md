# policy-v1.md: Agent Identity, Capability Policy, and Approvals

## Goals

- Enforce least privilege with explicit capability grants.
- Require human approval for irreversible or high-risk actions.
- Prevent runaway behavior via limits and quotas.
- Keep security posture consistent across local and cross-platform deployments.

---

## Policy Model (v1)

Policy is evaluated by the kernel before dispatching operations.

### Subjects
- `agent_id` (primary subject)
- optional `run_id` and `node_id` context

### Objects
- `capability` (e.g., `gmail.send`, `exchange.place_order`)
- `operation` (concrete connector op)

### Decision outcomes
- `allow`
- `deny`
- `require_approval`

---

## YAML Example

```yaml
policy_version: 1
policy_snapshot_id: pol_2026-03-05_a1

defaults:
  deny_by_default: true
  require_approval_for_irreversible: true
  rate_limits:
    per_agent_tool_calls_per_minute: 60
    per_agent_concurrent_ops: 4

agents:
  gmail.triage:
    allowed_capabilities:
      - gmail.read.metadata
      - gmail.read.body
      - gmail.send
    approval_required_ops:
      - gmail.send_draft
    constraints:
      gmail.send:
        allowed_recipient_domains: ["example.com", "company.com"]
        max_recipients: 10

  crypto.swing.v2:
    allowed_capabilities:
      - exchange.read
      - exchange.place_order
    approval_required_ops:
      - exchange.place_order
    constraints:
      exchange.place_order:
        max_notional_usd: 250
        allowed_symbols: ["BTC-USD", "ETH-USD"]
        max_orders_per_day: 3

tools:
  net.fetch:
    allowlist_domains:
      - news.ycombinator.com
      - rss.nytimes.com
      - arxiv.org
```

---

## Enforcement Order (deterministic)

1. Validate request schema and required fields.
2. Resolve `agent_id` policy record.
3. Check capability allowlist.
4. Apply operation constraints (symbols, domains, notional, recipients, etc.).
5. Apply global + agent rate limits.
6. Evaluate approval requirements.
7. Produce final decision + reason code.

---

## Approval UX Requirements

Approval prompts must include:
- who: `agent_id`
- what: `operation`
- why now: concise reason/context
- key params: e.g., recipient, symbol, notional
- impact summary: irreversible/risk note

Supported actions:
- approve once
- approve for run (time-bounded)
- deny once
- deny and block op for agent (policy override entry)

---

## Secret Handling (MUST)

- Secrets are stored only in connector services and OS/key-manager backends.
- Kernel and agents do not persist raw tokens/API keys.
- Logs/events must never include raw secret material.
- Policy evaluation uses metadata/claims, not credential payloads.

---

## Audit Requirements

Every decision emits structured audit events with:
- decision (`allow`/`deny`/`require_approval`)
- reason code
- policy snapshot id
- run/agent/operation correlation IDs
- timestamp (UTC)

Audit logs must be append-only and replayable.

---

## Cross-Platform Notes

- Policy file format is plain YAML + typed schema validation.
- Runtime storage paths and secret providers must be abstracted (no POSIX-only assumptions).
- Approval/session TTL semantics must be clock-safe (UTC timestamps).
