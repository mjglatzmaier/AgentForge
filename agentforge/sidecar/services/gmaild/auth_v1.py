"""Cross-platform gmail auth/token storage abstractions."""

from __future__ import annotations

import json
from typing import Protocol

from agentforge.sidecar.services.gmaild.contracts_v1 import GmailOAuthTokenV1


class OAuthCodeExchange(Protocol):
    """Exchanges one OAuth authorization code for token material."""

    def exchange_code(self, *, auth_code: str) -> GmailOAuthTokenV1: ...


class SecretStore(Protocol):
    """Secret storage abstraction (OS keychain or test doubles)."""

    def set_secret(self, *, service: str, account: str, secret: str) -> None: ...

    def get_secret(self, *, service: str, account: str) -> str | None: ...


class KeyringSecretStore:
    """Stores tokens in OS keychain via python-keyring when installed."""

    def set_secret(self, *, service: str, account: str, secret: str) -> None:
        keyring = _load_keyring()
        keyring.set_password(service, account, secret)

    def get_secret(self, *, service: str, account: str) -> str | None:
        keyring = _load_keyring()
        value = keyring.get_password(service, account)
        if value is None:
            return None
        return str(value)


class GmailAuthServiceV1:
    """Auth service used by agentctl auth gmail / gmaild auth paths."""

    _service_name = "agentforge.gmaild.oauth"

    def __init__(
        self,
        *,
        exchanger: OAuthCodeExchange,
        secret_store: SecretStore,
    ) -> None:
        self._exchanger = exchanger
        self._secret_store = secret_store

    def auth_with_code(self, *, account: str, auth_code: str) -> GmailOAuthTokenV1:
        token = self._exchanger.exchange_code(auth_code=auth_code)
        payload = json.dumps(token.model_dump(mode="json"), sort_keys=True)
        self._secret_store.set_secret(
            service=self._service_name,
            account=account,
            secret=payload,
        )
        return token

    def load_token(self, *, account: str) -> GmailOAuthTokenV1 | None:
        payload = self._secret_store.get_secret(
            service=self._service_name,
            account=account,
        )
        if payload is None:
            return None
        return GmailOAuthTokenV1.model_validate(json.loads(payload))


def _load_keyring() -> object:
    try:
        import keyring  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent.
        raise RuntimeError(
            "python-keyring is required for OS keychain token storage."
        ) from exc
    return keyring

