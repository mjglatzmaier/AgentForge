"""Gmail connector service package."""

from agentforge.sidecar.services.gmaild.auth_v1 import (
    GmailAuthServiceV1,
    KeyringSecretStore,
    OAuthCodeExchange,
    SecretStore,
)
from agentforge.sidecar.services.gmaild.connector_v1 import EmailBackend, GmailConnectorServiceV1
from agentforge.sidecar.services.gmaild.contracts_v1 import (
    EmailDraftCreateInputV1,
    EmailDraftRefV1,
    EmailMessageBodyV1,
    EmailMessageMetadataV1,
    EmailMessageSummaryV1,
    EmailSentRefV1,
    GmailOAuthTokenV1,
)

__all__ = [
    "EmailBackend",
    "EmailDraftCreateInputV1",
    "EmailDraftRefV1",
    "EmailMessageBodyV1",
    "EmailMessageMetadataV1",
    "EmailMessageSummaryV1",
    "EmailSentRefV1",
    "GmailAuthServiceV1",
    "GmailConnectorServiceV1",
    "GmailOAuthTokenV1",
    "KeyringSecretStore",
    "OAuthCodeExchange",
    "SecretStore",
]
