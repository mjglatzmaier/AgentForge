"""Typed contracts for exchanged v1 connector operations."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ExchangeApiCredentialsV1(BaseModel):
    api_key: str
    api_secret: str
    passphrase: str | None = None

    @field_validator("api_key", "api_secret", "passphrase")
    @classmethod
    def validate_non_empty_optional_strings(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("Credential fields must be non-empty when provided.")
        return normalized


class ExchangeBalanceV1(BaseModel):
    asset: str
    free: float
    locked: float = 0.0


class ExchangePositionV1(BaseModel):
    symbol: str
    quantity: float
    entry_price: float


class ExchangeOrderRequestV1(BaseModel):
    symbol: str
    side: Literal["buy", "sell"]
    notional_usd: float

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("symbol must be non-empty.")
        return normalized

    @field_validator("notional_usd")
    @classmethod
    def validate_notional(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("notional_usd must be > 0.")
        return value


class ExchangeOrderRefV1(BaseModel):
    order_id: str
    status: Literal["accepted", "rejected", "filled"] = "accepted"
    created_at_utc: datetime


class ExchangeRiskPolicyV1(BaseModel):
    max_notional_per_order_usd: float
    allowed_symbols: list[str] = Field(default_factory=list)
    max_orders_per_day: int
    daily_max_loss_usd: float | None = None

    @field_validator("max_notional_per_order_usd")
    @classmethod
    def validate_max_notional(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("max_notional_per_order_usd must be > 0.")
        return value

    @field_validator("allowed_symbols")
    @classmethod
    def validate_symbols(cls, value: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in value:
            item_norm = item.strip()
            if not item_norm:
                raise ValueError("allowed_symbols entries must be non-empty.")
            normalized.append(item_norm)
        return normalized

    @field_validator("max_orders_per_day")
    @classmethod
    def validate_max_orders_per_day(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_orders_per_day must be >= 1.")
        return value

    @field_validator("daily_max_loss_usd")
    @classmethod
    def validate_daily_max_loss(cls, value: float | None) -> float | None:
        if value is None:
            return None
        if value <= 0:
            raise ValueError("daily_max_loss_usd must be > 0 when provided.")
        return value
