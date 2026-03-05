"""Cross-platform exchanged credential storage abstractions."""

from __future__ import annotations

import json
from typing import Protocol

from agentforge.sidecar.services.exchanged.contracts_v1 import ExchangeApiCredentialsV1


class SecretStore(Protocol):
    """Secret storage abstraction (OS keychain or test doubles)."""

    def set_secret(self, *, service: str, account: str, secret: str) -> None: ...

    def get_secret(self, *, service: str, account: str) -> str | None: ...


class KeyringSecretStore:
    """Stores exchange credentials in OS keychain via python-keyring when installed."""

    def set_secret(self, *, service: str, account: str, secret: str) -> None:
        keyring = _load_keyring()
        keyring.set_password(service, account, secret)

    def get_secret(self, *, service: str, account: str) -> str | None:
        keyring = _load_keyring()
        value = keyring.get_password(service, account)
        if value is None:
            return None
        return str(value)


class ExchangeAuthServiceV1:
    """Stores and retrieves exchanged API credentials."""

    _service_name = "agentforge.exchanged.credentials"

    def __init__(self, *, secret_store: SecretStore) -> None:
        self._secret_store = secret_store

    def store_credentials(
        self,
        *,
        account: str,
        credentials: ExchangeApiCredentialsV1,
    ) -> ExchangeApiCredentialsV1:
        payload = json.dumps(credentials.model_dump(mode="json"), sort_keys=True)
        self._secret_store.set_secret(
            service=self._service_name,
            account=account,
            secret=payload,
        )
        return credentials

    def load_credentials(self, *, account: str) -> ExchangeApiCredentialsV1 | None:
        payload = self._secret_store.get_secret(
            service=self._service_name,
            account=account,
        )
        if payload is None:
            return None
        return ExchangeApiCredentialsV1.model_validate(json.loads(payload))


def _load_keyring() -> object:
    try:
        import keyring  # type: ignore
    except ImportError as exc:  # pragma: no cover - environment dependent.
        raise RuntimeError(
            "python-keyring is required for OS keychain credential storage."
        ) from exc
    return keyring
