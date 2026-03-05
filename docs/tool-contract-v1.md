# tool-contract-v1.md: Kernel ↔ Broker ↔ Connector Contract

## Purpose

Define a minimal, typed, versioned contract for invoking connector operations from the kernel through a broker.  
This contract is transport-agnostic (local HTTP, Unix socket, Named Pipe, gRPC wrapper, etc.).

## Design Constraints

- Deterministic and replay-safe.
- Deny-by-default: every operation must map to a declared capability.
- No secret material in payloads or logs.
- Portable across macOS/Linux/Windows.

---

## Core Entities

- **Kernel**: control plane decision point (policy, approvals, scheduling).
- **Broker**: routes typed requests/events; preserves correlation metadata.
- **Connector Service**: executes a bounded operation against an external system.

---

## Request Envelope (v1)

```json
{
  "schema_version": 1,
  "request_id": "req_01HV...",
  "run_id": "run_20260305_abc123",
  "node_id": "node_fetch_prices",
  "agent_id": "market.scanner.v1",
  "capability": "exchange.read",
  "operation": "exchange.get_ticker",
  "idempotency_key": "run_20260305_abc123:node_fetch_prices:exchange.get_ticker",
  "deadline_utc": "2026-03-05T02:00:00Z",
  "input": {
    "symbol": "BTC-USD"
  },
  "policy_context": {
    "policy_snapshot_id": "pol_2026-03-05_a1",
    "approval_token": null
  },
  "trace": {
    "correlation_id": "corr_...",
    "causation_id": "evt_..."
  }
}
```

### Required validation

- `schema_version == 1`
- `operation` must be declared by the target connector.
- `capability` must satisfy policy for `agent_id`.
- `deadline_utc` must be in the future and bounded by kernel timeout policy.
- `idempotency_key` required for non-read operations.

---

## Response Envelope (v1)

```json
{
  "schema_version": 1,
  "request_id": "req_01HV...",
  "status": "ok",
  "output": {
    "price": 64890.2,
    "as_of_utc": "2026-03-05T01:59:59Z"
  },
  "artifacts": [
    {
      "name": "ticker-snapshot",
      "type": "application/json",
      "path": "steps/02_node_fetch_prices/outputs/ticker.json"
    }
  ],
  "metrics": {
    "latency_ms": 128
  },
  "trace": {
    "correlation_id": "corr_..."
  }
}
```

`status` values:
- `ok`
- `error`
- `denied`
- `approval_required`
- `timeout`

---

## Error Taxonomy (bounded)

Standard error shape:

```json
{
  "code": "POLICY_DENIED",
  "message": "operation not allowed by current policy",
  "retryable": false,
  "details": {
    "operation": "exchange.place_order"
  }
}
```

Allowed `code` values in v1:
- `INVALID_REQUEST`
- `POLICY_DENIED`
- `APPROVAL_REQUIRED`
- `CONNECTOR_UNAVAILABLE`
- `CONNECTOR_TIMEOUT`
- `UPSTREAM_ERROR`
- `RATE_LIMITED`
- `INTERNAL_ERROR`

---

## Broker Event Requirements

Every request/response pair must emit structured broker events:

- `tool.requested`
- `tool.approval_required` (optional)
- `tool.started`
- `tool.completed` or `tool.failed`

Each event must include: `event_id`, `timestamp_utc`, `request_id`, `run_id`, `node_id`, `agent_id`, `operation`, and trace correlation fields.

---

## Security Requirements

- Connector auth tokens/keys never traverse this contract.
- Payload and logs must redact sensitive fields by policy.
- Kernel enforces operation-level allowlist before broker dispatch.
- Approval tokens are opaque, short-lived, and single-use unless policy explicitly allows run-scoped approval.

---

## Compatibility

- v1 is additive-only for minor revisions.
- Breaking changes require `schema_version: 2`.
- Connectors should ignore unknown fields to allow forward-compatible evolution.
