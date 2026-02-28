"""Shared parsing helpers for provider text responses."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ValidationError

from agentforge.providers.base import ProviderValidationError

_CODE_BLOCK_RE = re.compile(r"```(?:json)?\s*(.*?)```", re.IGNORECASE | re.DOTALL)


def parse_and_validate_response_text(
    raw_text: str, *, response_model: type[BaseModel], provider: str
) -> BaseModel:
    """Parse provider text into JSON and validate against response model."""
    excerpt = raw_text[:300]
    parsed_any = False
    first_validation_error: ValidationError | None = None
    for payload in iter_json_payload_candidates(raw_text):
        parsed_any = True
        try:
            return response_model.model_validate(payload)
        except ValidationError as exc:
            if first_validation_error is None:
                first_validation_error = exc
            continue

    if not parsed_any:
        raise ProviderValidationError(
            f"{provider} returned non-JSON output; raw excerpt: {excerpt}. "
            "Could not locate valid JSON object in model response."
        )

    raise ProviderValidationError(
        f"{provider} response failed schema validation; raw excerpt: {excerpt}"
    ) from first_validation_error


def parse_json_payload(raw_text: str) -> Any:
    """Best-effort JSON extraction supporting fenced or prefixed outputs."""
    for payload in iter_json_payload_candidates(raw_text):
        return payload
    raise ValueError("Could not locate valid JSON object in model response.")


def iter_json_payload_candidates(raw_text: str) -> list[Any]:
    """Return parsed JSON payload candidates in priority order."""
    text = raw_text.strip()
    candidate_texts = [text]
    candidate_texts.extend(match.group(1).strip() for match in _CODE_BLOCK_RE.finditer(text))

    decoder = json.JSONDecoder()
    payloads: list[Any] = []
    for candidate in candidate_texts:
        if not candidate:
            continue
        try:
            payloads.append(json.loads(candidate))
            continue
        except json.JSONDecodeError:
            pass

        # If content already starts as JSON, avoid falling back to nested object parsing.
        if candidate.lstrip().startswith(("{", "[")):
            continue

        for idx, ch in enumerate(candidate):
            if ch not in "{[":
                continue
            try:
                payload, end = decoder.raw_decode(candidate, idx)
            except json.JSONDecodeError:
                continue
            if candidate[end:].strip():
                continue
            payloads.append(payload)
            break
    return payloads
