"""exchanged connector v1 with approval-gated and risk-limited order execution."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Protocol

from agentforge.sidecar.services.exchanged.contracts_v1 import (
    ExchangeBalanceV1,
    ExchangeOrderRefV1,
    ExchangeOrderRequestV1,
    ExchangePositionV1,
    ExchangeRiskPolicyV1,
)


class ExchangeBackend(Protocol):
    """Provider-neutral backend interface for exchange APIs."""

    def get_balances(self) -> list[ExchangeBalanceV1]: ...

    def get_positions(self) -> list[ExchangePositionV1]: ...

    def place_order(self, *, order: ExchangeOrderRequestV1) -> ExchangeOrderRefV1: ...

    def realized_pnl_usd_today(self) -> float: ...


class ExchangeConnectorServiceV1:
    """Risk-limited exchange connector enforcing policy before order placement."""

    def __init__(
        self,
        *,
        backend: ExchangeBackend,
        risk_policy: ExchangeRiskPolicyV1,
    ) -> None:
        self._backend = backend
        self._risk_policy = risk_policy
        self._executed_order_dates_utc: list[str] = []

    def get_balances(self) -> list[ExchangeBalanceV1]:
        return self._backend.get_balances()

    def get_positions(self) -> list[ExchangePositionV1]:
        return self._backend.get_positions()

    def place_order(
        self,
        *,
        symbol: str,
        side: Literal["buy", "sell"],
        notional_usd: float,
        approved: bool = False,
    ) -> ExchangeOrderRefV1:
        if not approved:
            raise PermissionError("Approval required for place_order.")
        order = ExchangeOrderRequestV1(
            symbol=symbol,
            side=side,
            notional_usd=notional_usd,
        )
        self._enforce_risk_controls(order)
        result = self._backend.place_order(order=order)
        self._record_order_count_for_today()
        return result

    def _enforce_risk_controls(self, order: ExchangeOrderRequestV1) -> None:
        if order.notional_usd > self._risk_policy.max_notional_per_order_usd:
            raise PermissionError("Order exceeds max_notional_per_order_usd.")
        if self._risk_policy.allowed_symbols and order.symbol not in self._risk_policy.allowed_symbols:
            raise PermissionError("Order symbol is not in allowed_symbols.")
        if self._orders_placed_today_count() >= self._risk_policy.max_orders_per_day:
            raise PermissionError("Order rejected: max_orders_per_day reached.")
        if self._risk_policy.daily_max_loss_usd is not None:
            realized_pnl = self._backend.realized_pnl_usd_today()
            if realized_pnl <= -self._risk_policy.daily_max_loss_usd:
                raise PermissionError("Order rejected: daily_max_loss_usd guard triggered.")

    def _orders_placed_today_count(self) -> int:
        today_key = _utc_today_key()
        return sum(1 for item in self._executed_order_dates_utc if item == today_key)

    def _record_order_count_for_today(self) -> None:
        self._executed_order_dates_utc.append(_utc_today_key())


def _utc_today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")
