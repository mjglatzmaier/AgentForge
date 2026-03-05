"""File-backed approval gateway for side-car approval flow v1."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

from agentforge.sidecar.agentd.broker.events_store import append_run_event, create_run_event
from agentforge.sidecar.core.contracts.approval_v1 import (
    ApprovalListV1,
    ApprovalRecordV1,
    ApprovalStatus,
    ApprovalTokenStatus,
    ApprovalTokenValidationV1,
    ApprovalTokenV1,
)
from agentforge.sidecar.core.contracts.events_v1 import RunEventType
from agentforge.sidecar.core.contracts.tool_contract_v1 import ToolCallRequestV1


class ApprovalGatewayV1:
    """Persist and resolve approval decisions without global state."""

    def __init__(
        self,
        runs_root: str | Path,
        *,
        token_ttl_seconds: int = 600,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        if token_ttl_seconds <= 0:
            raise ValueError("token_ttl_seconds must be > 0.")
        self._runs_root = Path(runs_root)
        self._token_ttl_seconds = token_ttl_seconds
        self._now_provider = now_provider or (lambda: datetime.now(timezone.utc))

    def request(self, request: ToolCallRequestV1) -> ApprovalRecordV1:
        approvals, tokens = self._load_state()
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
            created_at_utc=self._now(),
        )
        approvals[approval_id] = created
        self._save_state(approvals, tokens)
        return created

    def get(self, approval_id: str) -> ApprovalRecordV1 | None:
        return self._load_state()[0].get(approval_id)

    def get_token(self, token_id: str) -> ApprovalTokenV1 | None:
        return self._load_state()[1].get(token_id)

    def list_pending(self) -> list[ApprovalRecordV1]:
        pending = [
            record
            for record in self._load_state()[0].values()
            if record.status is ApprovalStatus.PENDING
        ]
        pending.sort(key=lambda item: (item.created_at_utc, item.approval_id))
        return pending

    def approve(self, approval_id: str) -> ApprovalRecordV1:
        approvals, tokens = self._load_state()
        record = approvals.get(approval_id)
        if record is None:
            raise KeyError(f"Approval not found: {approval_id}")
        if record.status is ApprovalStatus.PENDING:
            now = self._now()
            token = _mint_approval_token(record, now, self._token_ttl_seconds)
            tokens[token.token_id] = token
            record = record.model_copy(
                update={
                    "status": ApprovalStatus.APPROVED,
                    "decided_at_utc": now,
                    "approval_token_id": token.token_id,
                    "approval_token_expires_at_utc": token.expires_at_utc,
                }
            )
            approvals[approval_id] = record
            self._save_state(approvals, tokens)
            self._append_token_event(
                run_id=record.run_id,
                event_type=RunEventType.APPROVAL_TOKEN_ISSUED,
                payload={
                    "approval_id": record.approval_id,
                    "approval_token": token.token_id,
                    "expires_at_utc": token.expires_at_utc.isoformat(),
                    "request_id": record.request_id,
                    "operation": record.operation,
                },
            )
        return record

    def deny(self, approval_id: str) -> ApprovalRecordV1:
        return self._set_decision(approval_id, ApprovalStatus.DENIED)

    def validate_token(
        self,
        token_id: str,
        request: ToolCallRequestV1,
    ) -> ApprovalTokenValidationV1:
        approvals, tokens = self._load_state()
        token = tokens.get(token_id)
        if token is None:
            self._append_token_event(
                run_id=request.run_id,
                event_type=RunEventType.APPROVAL_TOKEN_REJECTED,
                payload={"approval_token": token_id, "reason_code": "APPROVAL_TOKEN_INVALID"},
            )
            return ApprovalTokenValidationV1(valid=False, reason_code="APPROVAL_TOKEN_INVALID")

        if token.status is ApprovalTokenStatus.USED:
            self._append_token_event(
                run_id=request.run_id,
                event_type=RunEventType.APPROVAL_TOKEN_REJECTED,
                payload={"approval_token": token_id, "reason_code": "APPROVAL_TOKEN_USED"},
            )
            return ApprovalTokenValidationV1(valid=False, reason_code="APPROVAL_TOKEN_USED")

        now = self._now()
        if now >= token.expires_at_utc:
            token = token.model_copy(update={"status": ApprovalTokenStatus.EXPIRED})
            tokens[token.token_id] = token
            self._save_state(approvals, tokens)
            self._append_token_event(
                run_id=request.run_id,
                event_type=RunEventType.APPROVAL_TOKEN_EXPIRED,
                payload={"approval_token": token_id, "approval_id": token.approval_id},
            )
            return ApprovalTokenValidationV1(valid=False, reason_code="APPROVAL_TOKEN_EXPIRED")

        if not _token_matches_request(token, request):
            self._append_token_event(
                run_id=request.run_id,
                event_type=RunEventType.APPROVAL_TOKEN_REJECTED,
                payload={"approval_token": token_id, "reason_code": "APPROVAL_TOKEN_CONTEXT_MISMATCH"},
            )
            return ApprovalTokenValidationV1(
                valid=False,
                reason_code="APPROVAL_TOKEN_CONTEXT_MISMATCH",
            )

        return ApprovalTokenValidationV1(valid=True, token=token)

    def consume_token(
        self,
        token_id: str,
        request: ToolCallRequestV1,
    ) -> ApprovalTokenValidationV1:
        validation = self.validate_token(token_id=token_id, request=request)
        if not validation.valid or validation.token is None:
            return validation
        approvals, tokens = self._load_state()
        token = tokens[validation.token.token_id]
        consumed = token.model_copy(
            update={"status": ApprovalTokenStatus.USED, "used_at_utc": self._now()}
        )
        tokens[consumed.token_id] = consumed
        self._save_state(approvals, tokens)
        self._append_token_event(
            run_id=request.run_id,
            event_type=RunEventType.APPROVAL_TOKEN_USED,
            payload={
                "approval_token": consumed.token_id,
                "approval_id": consumed.approval_id,
                "request_id": request.request_id,
            },
        )
        return ApprovalTokenValidationV1(valid=True, token=consumed)

    def _set_decision(self, approval_id: str, status: ApprovalStatus) -> ApprovalRecordV1:
        approvals, tokens = self._load_state()
        record = approvals.get(approval_id)
        if record is None:
            raise KeyError(f"Approval not found: {approval_id}")
        if record.status is ApprovalStatus.PENDING:
            record = record.model_copy(
                update={
                    "status": status,
                    "decided_at_utc": self._now(),
                }
            )
            approvals[approval_id] = record
            self._save_state(approvals, tokens)
        return record

    def _load_state(self) -> tuple[dict[str, ApprovalRecordV1], dict[str, ApprovalTokenV1]]:
        store_path = _approval_store_path(self._runs_root)
        if not store_path.exists():
            return {}, {}
        payload = json.loads(store_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("Approval store root must be a mapping.")
        raw_records = payload.get("approvals", [])
        if not isinstance(raw_records, list):
            raise ValueError("Approval store 'approvals' must be a list.")
        raw_tokens = payload.get("tokens", [])
        if not isinstance(raw_tokens, list):
            raise ValueError("Approval store 'tokens' must be a list.")
        records: dict[str, ApprovalRecordV1] = {}
        tokens: dict[str, ApprovalTokenV1] = {}
        for item in raw_records:
            record = ApprovalRecordV1.model_validate(item)
            records[record.approval_id] = record
        for item in raw_tokens:
            token = ApprovalTokenV1.model_validate(item)
            tokens[token.token_id] = token
        return records, tokens

    def _save_state(
        self,
        approvals: dict[str, ApprovalRecordV1],
        tokens: dict[str, ApprovalTokenV1],
    ) -> None:
        store_path = _approval_store_path(self._runs_root)
        store_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "approvals": [approvals[key].model_dump(mode="json") for key in sorted(approvals)],
            "tokens": [tokens[key].model_dump(mode="json") for key in sorted(tokens)],
        }
        temp_path = store_path.with_suffix(f"{store_path.suffix}.tmp")
        temp_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
        temp_path.replace(store_path)

    def _append_token_event(
        self,
        *,
        run_id: str,
        event_type: RunEventType,
        payload: dict[str, object],
    ) -> None:
        append_run_event(
            self._runs_root / run_id,
            create_run_event(
                run_id=run_id,
                event_type=event_type,
                payload=payload,
            ),
        )

    def _now(self) -> datetime:
        return self._now_provider()


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


def _mint_approval_token(
    record: ApprovalRecordV1,
    now: datetime,
    token_ttl_seconds: int,
) -> ApprovalTokenV1:
    token_id = f"apt-{uuid4().hex}"
    return ApprovalTokenV1(
        token_id=token_id,
        approval_id=record.approval_id,
        request_id=record.request_id,
        run_id=record.run_id,
        node_id=record.node_id,
        agent_id=record.agent_id,
        operation=record.operation,
        capability=record.capability,
        status=ApprovalTokenStatus.ISSUED,
        issued_at_utc=now,
        expires_at_utc=now + timedelta(seconds=token_ttl_seconds),
    )


def _token_matches_request(token: ApprovalTokenV1, request: ToolCallRequestV1) -> bool:
    return (
        token.request_id == request.request_id
        and token.run_id == request.run_id
        and token.node_id == request.node_id
        and token.agent_id == request.agent_id
        and token.operation == request.operation
        and token.capability == request.capability
    )
