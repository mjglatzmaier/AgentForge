"""gmaild connector v1 with metadata-first safe defaults."""

from __future__ import annotations

from typing import Protocol

from agentforge.sidecar.services.gmaild.contracts_v1 import (
    EmailDraftCreateInputV1,
    EmailDraftRefV1,
    EmailMessageBodyV1,
    EmailMessageMetadataV1,
    EmailMessageSummaryV1,
    EmailSentRefV1,
)


class EmailBackend(Protocol):
    """Provider-neutral email backend interface for extensibility."""

    def list_messages(self, *, query: str, max_results: int) -> list[EmailMessageSummaryV1]: ...

    def get_message_metadata(self, *, message_id: str) -> EmailMessageMetadataV1: ...

    def get_message_body(self, *, message_id: str) -> EmailMessageBodyV1: ...

    def create_draft(self, *, draft: EmailDraftCreateInputV1) -> EmailDraftRefV1: ...

    def send_draft(self, *, draft_id: str) -> EmailSentRefV1: ...


class GmailConnectorServiceV1:
    """Safe-by-default connector implementation with approval-gated sensitive ops."""

    def __init__(self, *, backend: EmailBackend) -> None:
        self._backend = backend

    def list_messages(self, *, query: str, max_results: int = 20) -> list[EmailMessageSummaryV1]:
        if max_results < 1:
            raise ValueError("max_results must be >= 1.")
        return self._backend.list_messages(query=query, max_results=max_results)

    def get_message_metadata(self, *, message_id: str) -> EmailMessageMetadataV1:
        return self._backend.get_message_metadata(message_id=message_id)

    def get_message_body(self, *, message_id: str, approved: bool = False) -> EmailMessageBodyV1:
        if not approved:
            raise PermissionError("Approval required for get_message_body.")
        return self._backend.get_message_body(message_id=message_id)

    def create_draft(
        self,
        *,
        to: str,
        subject: str,
        body: str,
        require_approval: bool = False,
        approved: bool = False,
    ) -> EmailDraftRefV1:
        if require_approval and not approved:
            raise PermissionError("Approval required for create_draft.")
        payload = EmailDraftCreateInputV1(to=to, subject=subject, body=body)
        return self._backend.create_draft(draft=payload)

    def send_draft(self, *, draft_id: str, approved: bool = False) -> EmailSentRefV1:
        if not approved:
            raise PermissionError("Approval required for send_draft.")
        return self._backend.send_draft(draft_id=draft_id)

