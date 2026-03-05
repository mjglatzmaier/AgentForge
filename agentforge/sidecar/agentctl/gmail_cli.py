"""gmail-specific CLI helpers."""

from __future__ import annotations

from agentforge.sidecar.services.gmaild.auth_v1 import GmailAuthServiceV1
from agentforge.sidecar.services.gmaild.contracts_v1 import GmailOAuthTokenV1


def auth_gmail(
    *,
    auth_service: GmailAuthServiceV1,
    account: str,
    auth_code: str,
) -> GmailOAuthTokenV1:
    """CLI helper backing `agentctl auth gmail`."""

    return auth_service.auth_with_code(account=account, auth_code=auth_code)

