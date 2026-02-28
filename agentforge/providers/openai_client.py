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


def _openai_strictify_schema(schema: Any) -> Any:
    """
    OpenAI strict json_schema requirements:
      - For every object: additionalProperties must be false
      - For every object: required must exist and include every key in properties
    """
    if isinstance(schema, dict):
        # recurse
        for k, v in list(schema.items()):
            schema[k] = _openai_strictify_schema(v)

        if schema.get("type") == "object" or "properties" in schema:
            props = schema.get("properties")
            if isinstance(props, dict):
                # disallow extra keys
                schema["additionalProperties"] = False
                # require every key that appears in properties
                schema["required"] = list(props.keys())

        return schema

    if isinstance(schema, list):
        return [_openai_strictify_schema(x) for x in schema]

    return schema

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

        # Keep prompts small; don't inline the schema here.
        system_prompt = request.system_prompt or ""
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": request.prompt},
        ]

        schema_json = _openai_strictify_schema(response_model.model_json_schema())

        payload: dict[str, Any] = {
            "model": model_name,
            "messages": messages,

            # Structured Outputs (schema adherence)
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": response_model.__name__,
                    "schema": schema_json,
                    "strict": True,
                },
            },
        }

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

        # Helpful diagnostics for truncation
        try:
            finish_reason = body.get("choices", [{}])[0].get("finish_reason")
        except Exception:
            finish_reason = None

        raw_text = _extract_openai_text(body)

        # If still malformed, include finish_reason + tail excerpt for debugging
        try:
            parsed = _parse_and_validate(raw_text, response_model=response_model, provider=self.name)
        except ProviderValidationError as exc:
            tail = raw_text[-300:] if isinstance(raw_text, str) else ""
            raise ProviderValidationError(
                f"{exc}. finish_reason={finish_reason}. tail_excerpt={tail}"
            ) from exc

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
