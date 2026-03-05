"""Append-only structured audit store for side-car decisions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from agentforge.sidecar.core.contracts.audit_v1 import AuditEventV1
from agentforge.sidecar.core.redaction_v1 import redact_sensitive_data


def create_audit_event(
    *,
    actor: str,
    decision: str,
    reason_code: str,
    run_id: str | None = None,
    request_id: str | None = None,
    details: dict[str, object] | None = None,
) -> AuditEventV1:
    return AuditEventV1(
        event_id=f"aud-{uuid4().hex}",
        timestamp_utc=datetime.now(timezone.utc),
        actor=actor,
        run_id=run_id,
        request_id=request_id,
        decision=decision,
        reason_code=reason_code,
        details=redact_sensitive_data(details or {}),
    )


def append_audit_event(runs_root: str | Path, event: AuditEventV1) -> Path:
    log_path = _audit_log_path(runs_root)
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(event.model_dump_json() + "\n")
    return log_path


def load_audit_events(runs_root: str | Path) -> list[AuditEventV1]:
    log_path = _audit_log_path(runs_root)
    if not log_path.exists():
        return []
    events: list[AuditEventV1] = []
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(AuditEventV1.model_validate(json.loads(line)))
    return events


def _audit_log_path(runs_root: str | Path) -> Path:
    return Path(runs_root) / "_audit" / "audit.jsonl"
