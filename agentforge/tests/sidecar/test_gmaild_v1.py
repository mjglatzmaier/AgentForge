from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agentforge.sidecar.agentctl.gmail_cli import auth_gmail
from agentforge.sidecar.services.gmaild import (
    EmailBackend,
    EmailDraftCreateInputV1,
    EmailDraftRefV1,
    EmailMessageBodyV1,
    EmailMessageMetadataV1,
    EmailMessageSummaryV1,
    EmailSentRefV1,
    GmailAuthServiceV1,
    GmailConnectorServiceV1,
    GmailOAuthTokenV1,
)


class _FakeExchanger:
    def exchange_code(self, *, auth_code: str) -> GmailOAuthTokenV1:
        return GmailOAuthTokenV1(
            access_token=f"access-{auth_code}",
            refresh_token=f"refresh-{auth_code}",
        )


class _MemorySecretStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], str] = {}

    def set_secret(self, *, service: str, account: str, secret: str) -> None:
        self._items[(service, account)] = secret

    def get_secret(self, *, service: str, account: str) -> str | None:
        return self._items.get((service, account))


class _FakeBackend(EmailBackend):
    def __init__(self) -> None:
        self.create_calls = 0
        self.send_calls = 0

    def list_messages(self, *, query: str, max_results: int) -> list[EmailMessageSummaryV1]:
        return [
            EmailMessageSummaryV1(
                message_id="msg-1",
                thread_id="thr-1",
                from_address="sender@example.com",
                subject=f"subject {query}",
                snippet="short snippet only",
                received_at_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
            )
        ][:max_results]

    def get_message_metadata(self, *, message_id: str) -> EmailMessageMetadataV1:
        return EmailMessageMetadataV1(
            message_id=message_id,
            thread_id="thr-1",
            headers={"subject": "hello", "from": "sender@example.com"},
        )

    def get_message_body(self, *, message_id: str) -> EmailMessageBodyV1:
        return EmailMessageBodyV1(message_id=message_id, body_text="full message body")

    def create_draft(self, *, draft: EmailDraftCreateInputV1) -> EmailDraftRefV1:
        self.create_calls += 1
        return EmailDraftRefV1(draft_id="drf-1")

    def send_draft(self, *, draft_id: str) -> EmailSentRefV1:
        self.send_calls += 1
        return EmailSentRefV1(message_id="msg-sent-1")


def test_auth_gmail_stores_token_via_secret_store() -> None:
    auth_service = GmailAuthServiceV1(exchanger=_FakeExchanger(), secret_store=_MemorySecretStore())
    token = auth_gmail(auth_service=auth_service, account="me@example.com", auth_code="code-1")
    loaded = auth_service.load_token(account="me@example.com")

    assert token.access_token == "access-code-1"
    assert loaded is not None
    assert loaded.access_token == token.access_token


def test_gmail_connector_metadata_first_and_body_on_demand() -> None:
    connector = GmailConnectorServiceV1(backend=_FakeBackend())
    summaries = connector.list_messages(query="in:inbox", max_results=1)
    metadata = connector.get_message_metadata(message_id="msg-1")

    assert len(summaries) == 1
    assert summaries[0].snippet
    assert metadata.headers["subject"] == "hello"
    with pytest.raises(PermissionError):
        connector.get_message_body(message_id="msg-1")
    assert connector.get_message_body(message_id="msg-1", approved=True).body_text == "full message body"


def test_gmail_connector_draft_and_send_are_safe_by_default() -> None:
    backend = _FakeBackend()
    connector = GmailConnectorServiceV1(backend=backend)

    draft = connector.create_draft(
        to="receiver@example.com",
        subject="Draft subject",
        body="Draft body",
    )
    assert draft.draft_id == "drf-1"
    assert backend.create_calls == 1
    assert backend.send_calls == 0

    with pytest.raises(PermissionError):
        connector.send_draft(draft_id=draft.draft_id)
    sent = connector.send_draft(draft_id=draft.draft_id, approved=True)
    assert sent.message_id == "msg-sent-1"
    assert backend.send_calls == 1

