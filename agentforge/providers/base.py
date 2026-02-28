"""Provider-agnostic LLM interface primitives."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar, cast

from pydantic import BaseModel, Field

TModel = TypeVar("TModel", bound=BaseModel)


class LlmRequest(BaseModel):
    """Structured request envelope for provider calls."""

    system_prompt: str | None = None
    prompt: str
    response_model: type[BaseModel]
    model: str | None = None
    temperature: float | None = None
    max_output_tokens: int | None = None
    seed: int | None = None
    timeout_s: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LlmResult(BaseModel, Generic[TModel]):
    """Structured provider response with parsed model payload."""

    parsed: TModel
    raw_text: str
    provider: str
    model: str
    usage: dict[str, int] = Field(default_factory=dict)
    latency_ms: int | None = None
    request_id: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ProviderError(Exception):
    """Base class for provider-related errors."""


class ProviderTransientError(ProviderError):
    """Retryable provider error."""


class ProviderPermanentError(ProviderError):
    """Non-retryable provider error."""


class ProviderValidationError(ProviderError):
    """Raised when provider output fails structured validation expectations."""


class BaseProvider(ABC):
    """Abstract provider interface for structured generation."""

    name: str = "base"

    @abstractmethod
    def generate(self, request: LlmRequest) -> LlmResult[BaseModel]:
        """Execute one provider request."""

    def generate_json(
        self,
        prompt: str,
        response_model: type[TModel],
        *,
        system_prompt: str | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
        seed: int | None = None,
        timeout_s: float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> LlmResult[TModel]:
        """Convenience wrapper for structured JSON-style requests."""
        request = LlmRequest(
            system_prompt=system_prompt,
            prompt=prompt,
            response_model=response_model,
            model=model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            seed=seed,
            timeout_s=timeout_s,
            metadata=dict(metadata or {}),
        )
        result = self.generate(request)
        if not isinstance(result.parsed, response_model):
            raise ProviderValidationError(
                f"Provider '{self.name}' returned parsed model type "
                f"{type(result.parsed).__name__}, expected {response_model.__name__}."
            )
        return cast(LlmResult[TModel], result)


__all__ = [
    "BaseProvider",
    "LlmRequest",
    "LlmResult",
    "ProviderError",
    "ProviderPermanentError",
    "ProviderTransientError",
    "ProviderValidationError",
]
