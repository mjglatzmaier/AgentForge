"""Sensitive-value redaction helpers for side-car logs and events."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

DEFAULT_SENSITIVE_KEY_PATTERNS: tuple[str, ...] = (
    "token",
    "secret",
    "api_key",
    "authorization",
)


def redact_sensitive_data(
    value: Any,
    *,
    sensitive_key_patterns: tuple[str, ...] = DEFAULT_SENSITIVE_KEY_PATTERNS,
    replacement: str = "[REDACTED]",
) -> Any:
    """Redact nested mapping values when keys match sensitive patterns."""

    if isinstance(value, Mapping):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_sensitive_key(key_text, sensitive_key_patterns):
                redacted[key_text] = replacement
            else:
                redacted[key_text] = redact_sensitive_data(
                    item,
                    sensitive_key_patterns=sensitive_key_patterns,
                    replacement=replacement,
                )
        return redacted

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [
            redact_sensitive_data(
                item,
                sensitive_key_patterns=sensitive_key_patterns,
                replacement=replacement,
            )
            for item in value
        ]

    return value


def _is_sensitive_key(key: str, patterns: tuple[str, ...]) -> bool:
    key_lower = key.lower()
    return any(pattern in key_lower for pattern in patterns)
