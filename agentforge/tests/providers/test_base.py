from __future__ import annotations

import pytest
from pydantic import BaseModel

from agentforge.providers.base import (
    BaseProvider,
    LlmRequest,
    LlmResult,
    ProviderError,
    ProviderPermanentError,
    ProviderTransientError,
    ProviderValidationError,
)


class DemoResponse(BaseModel):
    value: str


class OtherResponse(BaseModel):
    number: int


class _DummyProvider(BaseProvider):
    name = "dummy"

    def __init__(self, parsed: BaseModel) -> None:
        self._parsed = parsed
        self.last_request: LlmRequest | None = None

    def generate(self, request: LlmRequest) -> LlmResult[BaseModel]:
        self.last_request = request
        return LlmResult(
            parsed=self._parsed,
            raw_text='{"ok": true}',
            provider=self.name,
            model=request.model or "dummy-model",
            usage={"prompt_tokens": 10, "completion_tokens": 5},
        )


def test_generate_json_builds_request_and_returns_typed_result() -> None:
    provider = _DummyProvider(parsed=DemoResponse(value="ok"))

    result = provider.generate_json(
        prompt="return json",
        response_model=DemoResponse,
        system_prompt="system",
        model="demo-1",
        temperature=0.2,
        max_output_tokens=128,
        seed=123,
        timeout_s=5.0,
        metadata={"run_id": "run-1"},
    )

    assert isinstance(result.parsed, DemoResponse)
    assert result.parsed.value == "ok"
    assert result.provider == "dummy"
    assert provider.last_request is not None
    assert provider.last_request.response_model is DemoResponse
    assert provider.last_request.metadata == {"run_id": "run-1"}


def test_generate_json_raises_provider_validation_error_for_wrong_model() -> None:
    provider = _DummyProvider(parsed=OtherResponse(number=1))

    with pytest.raises(ProviderValidationError):
        provider.generate_json(prompt="return json", response_model=DemoResponse)


def test_error_hierarchy_and_defaults_are_well_typed() -> None:
    request = LlmRequest(prompt="hello", response_model=DemoResponse)
    result = LlmResult(
        parsed=DemoResponse(value="ok"),
        raw_text='{"value":"ok"}',
        provider="dummy",
        model="demo",
    )

    assert request.metadata == {}
    assert result.usage == {}
    assert result.warnings == []
    assert issubclass(ProviderTransientError, ProviderError)
    assert issubclass(ProviderPermanentError, ProviderError)
