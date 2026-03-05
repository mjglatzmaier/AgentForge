"""File-backed approval gateway for side-car approval flow v1."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

from agentforge.sidecar.core.contracts.approval_v1 import (
    ApprovalListV1,
    ApprovalRecordV1,
    ApprovalStatus,
)
from agentforge.sidecar.core.contracts.tool_contract_v1 import ToolCallRequestV1


class ApprovalGatewayV1:
    """Persist and resolve approval decisions without global state."""

    def __init__(self, runs_root: str | Path) -> None:
        self._runs_root = Path(runs_root)

    def request(self, request: ToolCallRequestV1) -> ApprovalRecordV1:
        approvals = self._load_records()
        approval_id = _stable_approval_id(request)
        existing = approvals.get(approval_id)
        if existing is not None:
            return existing

        created = ApprovalRecordV1(
            approval_id=approval_id,
            request_id=request.request_id,
            run_id=request.run_id,
            node_id=request.node_id,
            agent_id=request.agent_id,
            operation=request.operation,
            capability=request.capability,
            status=ApprovalStatus.PENDING,
            created_at_utc=datetime.now(timezone.utc),
        )
        approvals[approval_id] = created
        self._save_records(approvals)
        return created

    def get(self, approval_id: str) -> ApprovalRecordV1 | None:
        return self._load_records().get(approval_id)

    def list_pending(self) -> list[ApprovalRecordV1]:
        pending = [
            record
            for record in self._load_records().values()
            if record.status is ApprovalStatus.PENDING
        ]
        pending.sort(key=lambda item: (item.created_at_utc, item.approval_id))
        return pending

    def approve(self, approval_id: str) -> ApprovalRecordV1:
        return self._set_decision(approval_id, ApprovalStatus.APPROVED)

    def deny(self, approval_id: str) -> ApprovalRecordV1:
        return self._set_decision(approval_id, ApprovalStatus.DENIED)

    def _set_decision(self, approval_id: str, status: ApprovalStatus) -> ApprovalRecordV1:
        approvals = self._load_records()
        record = approvals.get(approval_id)
        if record is None:
            raise KeyError(f"Approval not found: {approval_id}")
        if record.status is ApprovalStatus.PENDING:
            record = record.model_copy(
                update={
                    "status": status,
                    "decided_at_utc": datetime.now(timezone.utc),
                }
            )
            approvals[approval_id] = record
            self._save_records(approvals)
        return record

    def _load_records(self) -> dict[str, ApprovalRecordV1]:
        store_path = _approval_store_path(self._runs_root)
        if not store_path.exists():
            return {}
        payload = json.loads(store_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Approval store root must be a mapping.")
        raw_records = payload.get("approvals", [])
        if not isinstance(raw_records, list):
            raise ValueError("Approval store 'approvals' must be a list.")
        records: dict[str, ApprovalRecordV1] = {}
        for item in raw_records:
            record = ApprovalRecordV1.model_validate(item)
            records[record.approval_id] = record
        return records

    def _save_records(self, records: dict[str, ApprovalRecordV1]) -> None:
        store_path = _approval_store_path(self._runs_root)
        store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "approvals": [
                records[key].model_dump(mode="json")
                for key in sorted(records)
            ],
        }
        temp_path = store_path.with_suffix(f"{store_path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(store_path)


def list_pending_approvals(runs_root: str | Path) -> ApprovalListV1:
    gateway = ApprovalGatewayV1(runs_root)
    return ApprovalListV1(approvals=gateway.list_pending())


def _approval_store_path(runs_root: Path) -> Path:
    return runs_root / "_approvals" / "approvals.json"


def _stable_approval_id(request: ToolCallRequestV1) -> str:
    payload = (
        f"{request.run_id}|{request.request_id}|{request.node_id}|"
        f"{request.agent_id}|{request.operation}|{request.capability}"
    )
    return f"apr-{sha256(payload.encode('utf-8')).hexdigest()[:20]}"

