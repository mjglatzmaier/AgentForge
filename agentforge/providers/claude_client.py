"""Anthropic Claude provider implementation."""

from __future__ import annotations

import json
import os
from time import perf_counter
from typing import Any

import httpx
from pydantic import BaseModel, ValidationError

from agentforge.providers.base import (
    BaseProvider,
    LlmRequest,
    LlmResult,
    ProviderPermanentError,
    ProviderTransientError,
    ProviderValidationError,
)


class ClaudeProvider(BaseProvider):
    """Minimal Anthropic messages API provider for structured output."""

    name = "claude"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "claude-3-5-haiku-latest",
        base_url: str = "https://api.anthropic.com/v1/messages",
    ) -> None:
        self._api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        self._default_model = model
        self._base_url = base_url

    def generate(self, request: LlmRequest) -> LlmResult[BaseModel]:
        if not self._api_key:
            raise ProviderPermanentError("ANTHROPIC_API_KEY is not set.")

        model_name = request.model or self._default_model
        timeout_s = request.timeout_s if request.timeout_s is not None else 30.0
        response_model = request.response_model
        strict_instruction = (
            "Return ONLY valid JSON matching this schema exactly. "
            f"Schema: {json.dumps(response_model.model_json_schema(), sort_keys=True)}"
        )

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": [{"role": "user", "content": request.prompt}],
            "max_tokens": request.max_output_tokens if request.max_output_tokens is not None else 512,
            "system": "\n\n".join(
                part for part in [request.system_prompt or "", strict_instruction] if part
            ),
        }
        if request.temperature is not None:
            payload["temperature"] = request.temperature

        started = perf_counter()
        try:
            response = httpx.post(
                self._base_url,
                headers={
                    "x-api-key": self._api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json=payload,
                timeout=timeout_s,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTransientError(f"Claude request timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            message = f"Claude HTTP error {status}: {exc.response.text[:300]}"
            if status >= 500 or status == 429:
                raise ProviderTransientError(message) from exc
            raise ProviderPermanentError(message) from exc
        except httpx.RequestError as exc:
            raise ProviderTransientError(f"Claude request failed: {exc}") from exc

        latency_ms = int((perf_counter() - started) * 1000)
        body = response.json()
        raw_text = _extract_claude_text(body)
        parsed = _parse_and_validate(raw_text, response_model=response_model, provider=self.name)
        usage = _extract_usage(body)
        request_id = response.headers.get("request-id") or body.get("id")

        return LlmResult(
            parsed=parsed,
            raw_text=raw_text,
            provider=self.name,
            model=str(body.get("model") or model_name),
            usage=usage,
            latency_ms=latency_ms,
            request_id=str(request_id) if request_id is not None else None,
            warnings=[],
        )


def _extract_claude_text(body: dict[str, Any]) -> str:
    content = body.get("content")
    if not isinstance(content, list):
        raise ProviderValidationError("Claude response missing content blocks.")
    texts: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            text = block.get("text")
            if isinstance(text, str):
                texts.append(text)
    if not texts:
        raise ProviderValidationError("Claude response did not include text content.")
    return "".join(texts)


def _parse_and_validate(raw_text: str, *, response_model: type[BaseModel], provider: str) -> BaseModel:
    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        excerpt = raw_text[:300]
        raise ProviderValidationError(
            f"{provider} returned non-JSON output; raw excerpt: {excerpt}"
        ) from exc
    try:
        return response_model.model_validate(payload)
    except ValidationError as exc:
        excerpt = raw_text[:300]
        raise ProviderValidationError(
            f"{provider} response failed schema validation; raw excerpt: {excerpt}"
        ) from exc


def _extract_usage(body: dict[str, Any]) -> dict[str, int]:
    usage_raw = body.get("usage")
    if not isinstance(usage_raw, dict):
        return {}
    usage: dict[str, int] = {}
    input_tokens = usage_raw.get("input_tokens")
    output_tokens = usage_raw.get("output_tokens")
    if isinstance(input_tokens, int):
        usage["prompt_tokens"] = input_tokens
    if isinstance(output_tokens, int):
        usage["completion_tokens"] = output_tokens
    return usage
