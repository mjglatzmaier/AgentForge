from __future__ import annotations

from datetime import datetime, timezone

import pytest

from agentforge.sidecar.services.exchanged import (
    ExchangeApiCredentialsV1,
    ExchangeAuthServiceV1,
    ExchangeBackend,
    ExchangeBalanceV1,
    ExchangeConnectorServiceV1,
    ExchangeOrderRefV1,
    ExchangeOrderRequestV1,
    ExchangePositionV1,
    ExchangeRiskPolicyV1,
)


class _MemorySecretStore:
    def __init__(self) -> None:
        self._items: dict[tuple[str, str], str] = {}

    def set_secret(self, *, service: str, account: str, secret: str) -> None:
        self._items[(service, account)] = secret

    def get_secret(self, *, service: str, account: str) -> str | None:
        return self._items.get((service, account))


class _FakeExchangeBackend(ExchangeBackend):
    def __init__(self) -> None:
        self.orders: list[ExchangeOrderRequestV1] = []
        self._realized_pnl = 0.0

    def get_balances(self) -> list[ExchangeBalanceV1]:
        return [ExchangeBalanceV1(asset="USD", free=1200.0, locked=0.0)]

    def get_positions(self) -> list[ExchangePositionV1]:
        return [ExchangePositionV1(symbol="BTC-USD", quantity=0.1, entry_price=50000.0)]

    def place_order(self, *, order: ExchangeOrderRequestV1) -> ExchangeOrderRefV1:
        self.orders.append(order)
        return ExchangeOrderRefV1(
            order_id=f"ord-{len(self.orders)}",
            status="accepted",
            created_at_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )

    def realized_pnl_usd_today(self) -> float:
        return self._realized_pnl

    def set_realized_pnl_usd_today(self, value: float) -> None:
        self._realized_pnl = value


def _risk_policy() -> ExchangeRiskPolicyV1:
    return ExchangeRiskPolicyV1(
        max_notional_per_order_usd=500.0,
        allowed_symbols=["BTC-USD", "ETH-USD"],
        max_orders_per_day=2,
        daily_max_loss_usd=100.0,
    )


def test_exchange_auth_service_stores_credentials() -> None:
    service = ExchangeAuthServiceV1(secret_store=_MemorySecretStore())
    creds = ExchangeApiCredentialsV1(api_key="key-1", api_secret="secret-1")

    stored = service.store_credentials(account="acct-1", credentials=creds)
    loaded = service.load_credentials(account="acct-1")
    assert stored.api_key == "key-1"
    assert loaded is not None
    assert loaded.api_secret == "secret-1"


def test_exchange_connector_exposes_balances_and_positions() -> None:
    connector = ExchangeConnectorServiceV1(backend=_FakeExchangeBackend(), risk_policy=_risk_policy())
    assert connector.get_balances()[0].asset == "USD"
    assert connector.get_positions()[0].symbol == "BTC-USD"


def test_exchange_connector_place_order_requires_approval() -> None:
    connector = ExchangeConnectorServiceV1(backend=_FakeExchangeBackend(), risk_policy=_risk_policy())
    with pytest.raises(PermissionError):
        connector.place_order(symbol="BTC-USD", side="buy", notional_usd=100.0)


def test_exchange_connector_enforces_risk_controls() -> None:
    backend = _FakeExchangeBackend()
    connector = ExchangeConnectorServiceV1(backend=backend, risk_policy=_risk_policy())

    with pytest.raises(PermissionError):
        connector.place_order(symbol="DOGE-USD", side="buy", notional_usd=100.0, approved=True)
    with pytest.raises(PermissionError):
        connector.place_order(symbol="BTC-USD", side="buy", notional_usd=600.0, approved=True)

    assert connector.place_order(symbol="BTC-USD", side="buy", notional_usd=100.0, approved=True).order_id
    assert connector.place_order(symbol="ETH-USD", side="sell", notional_usd=100.0, approved=True).order_id
    with pytest.raises(PermissionError):
        connector.place_order(symbol="BTC-USD", side="buy", notional_usd=50.0, approved=True)


def test_exchange_connector_daily_max_loss_guard() -> None:
    backend = _FakeExchangeBackend()
    backend.set_realized_pnl_usd_today(-150.0)
    connector = ExchangeConnectorServiceV1(backend=backend, risk_policy=_risk_policy())

    with pytest.raises(PermissionError):
        connector.place_order(symbol="BTC-USD", side="buy", notional_usd=100.0, approved=True)

