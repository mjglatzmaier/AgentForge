"""Typed contracts for gmaild v1 connector operations."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class GmailOAuthTokenV1(BaseModel):
    access_token: str
    refresh_token: str | None = None
    expires_at_utc: datetime | None = None

    @field_validator("access_token", "refresh_token")
    @classmethod
    def validate_non_empty_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("OAuth token string fields must be non-empty when provided.")
        return normalized


class EmailMessageSummaryV1(BaseModel):
    message_id: str
    thread_id: str
    from_address: str
    subject: str
    snippet: str
    received_at_utc: datetime


class EmailMessageMetadataV1(BaseModel):
    message_id: str
    thread_id: str
    headers: dict[str, str] = Field(default_factory=dict)


class EmailMessageBodyV1(BaseModel):
    message_id: str
    body_text: str


class EmailDraftRefV1(BaseModel):
    draft_id: str


class EmailSentRefV1(BaseModel):
    message_id: str


class EmailDraftCreateInputV1(BaseModel):
    to: str
    subject: str
    body: str

    @field_validator("subject", "body")
    @classmethod
    def validate_non_empty_strings(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Draft fields must be non-empty.")
        return normalized

    @field_validator("to")
    @classmethod
    def validate_to_address(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or "@" not in normalized:
            raise ValueError("Draft recipient address must look like an email address.")
        return normalized
