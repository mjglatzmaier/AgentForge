"""OpenAI provider implementation."""

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


class OpenAIProvider(BaseProvider):
    """Minimal OpenAI chat-completions provider for structured output."""

    name = "openai"

    def __init__(
        self,
        *,
        api_key: str | None = None,
        model: str = "gpt-4o-mini",
        base_url: str = "https://api.openai.com/v1/chat/completions",
    ) -> None:
        self._api_key = api_key or os.getenv("OPENAI_API_KEY")
        self._default_model = model
        self._base_url = base_url

    def generate(self, request: LlmRequest) -> LlmResult[BaseModel]:
        if not self._api_key:
            raise ProviderPermanentError("OPENAI_API_KEY is not set.")

        model_name = request.model or self._default_model
        timeout_s = request.timeout_s if request.timeout_s is not None else 30.0
        response_model = request.response_model
        schema_json = response_model.model_json_schema()
        system_prompt = request.system_prompt or ""
        strict_instruction = (
            "Return ONLY valid JSON that matches this schema exactly. "
            f"Schema: {json.dumps(schema_json, sort_keys=True)}"
        )
        messages: list[dict[str, str]] = [
            {"role": "system", "content": "\n\n".join(part for part in [system_prompt, strict_instruction] if part)},
            {"role": "user", "content": request.prompt},
        ]

        payload: dict[str, Any] = {"model": model_name, "messages": messages}
        if request.temperature is not None:
            payload["temperature"] = request.temperature
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if request.seed is not None:
            payload["seed"] = request.seed

        started = perf_counter()
        try:
            response = httpx.post(
                self._base_url,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=timeout_s,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise ProviderTransientError(f"OpenAI request timed out: {exc}") from exc
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            message = f"OpenAI HTTP error {status}: {exc.response.text[:300]}"
            if status >= 500 or status == 429:
                raise ProviderTransientError(message) from exc
            raise ProviderPermanentError(message) from exc
        except httpx.RequestError as exc:
            raise ProviderTransientError(f"OpenAI request failed: {exc}") from exc

        latency_ms = int((perf_counter() - started) * 1000)
        body = response.json()
        raw_text = _extract_openai_text(body)
        parsed = _parse_and_validate(raw_text, response_model=response_model, provider=self.name)
        usage = _extract_usage(body)
        request_id = body.get("id") or response.headers.get("x-request-id")

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


def _extract_openai_text(body: dict[str, Any]) -> str:
    choices = body.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ProviderValidationError("OpenAI response missing choices.")
    message = choices[0].get("message", {})
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [item.get("text", "") for item in content if isinstance(item, dict)]
        return "".join(parts)
    raise ProviderValidationError("OpenAI response missing textual content.")


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
    for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
        value = usage_raw.get(key)
        if isinstance(value, int):
            usage[key] = value
    return usage
