from __future__ import annotations

import pytest
from pydantic import BaseModel

from agentforge.providers.base import ProviderPermanentError, ProviderValidationError
from agentforge.providers.claude_client import ClaudeProvider
from agentforge.providers.openai_client import OpenAIProvider


class TinySchema(BaseModel):
    message: str


class _FakeResponse:
    def __init__(self, payload: dict, headers: dict[str, str] | None = None) -> None:
        self._payload = payload
        self.headers = headers or {}
        self.text = str(payload)

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


# def test_openai_provider_returns_validated_result(monkeypatch: pytest.MonkeyPatch) -> None:
#     calls: list[dict] = []

#     def _fake_post(url: str, **kwargs):
#         calls.append(kwargs["json"])
#         return _FakeResponse(
#             {
#                 "id": "req_openai_1",
#                 "model": "gpt-4o-mini",
#                 "choices": [{"message": {"content": '{"message":"hello"}'}}],
#                 "usage": {"prompt_tokens": 12, "completion_tokens": 8},
#             },
#             headers={"x-request-id": "hdr-openai-1"},
#         )

#     monkeypatch.setenv("OPENAI_API_KEY", "test-key")
#     monkeypatch.setattr("agentforge.providers.openai_client.httpx.post", _fake_post)

#     provider = OpenAIProvider()
#     result = provider.generate_json("Say hello", TinySchema)

#     assert result.parsed.message == "hello"
#     assert result.provider == "openai"
#     assert result.request_id == "req_openai_1"
#     assert result.usage == {"prompt_tokens": 12, "completion_tokens": 8}
    #assert "Schema:" in calls[0]["messages"][0]["content"]
    #assert calls[0]["response_format"]["type"] == "json_schema"
    #assert calls[0]["response_format"]["json_schema"]["strict"] is True


def test_claude_provider_returns_validated_result(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict] = []

    def _fake_post(url: str, **kwargs):
        calls.append(kwargs["json"])
        return _FakeResponse(
            {
                "id": "msg_1",
                "model": "claude-3-5-haiku-latest",
                "content": [{"type": "text", "text": '{"message":"hi"}'}],
                "usage": {"input_tokens": 9, "output_tokens": 4},
            },
            headers={"request-id": "req-claude-1"},
        )

    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr("agentforge.providers.claude_client.httpx.post", _fake_post)

    provider = ClaudeProvider()
    result = provider.generate_json("Say hi", TinySchema)

    assert result.parsed.message == "hi"
    assert result.provider == "claude"
    assert result.request_id == "req-claude-1"
    assert result.usage == {"prompt_tokens": 9, "completion_tokens": 4}
    assert "Schema:" in calls[0]["system"]


# def test_openai_provider_parses_fenced_json(monkeypatch: pytest.MonkeyPatch) -> None:
#     monkeypatch.setenv("OPENAI_API_KEY", "test-key")
#     monkeypatch.setattr(
#         "agentforge.providers.openai_client.httpx.post",
#         lambda *args, **kwargs: _FakeResponse(
#             {
#                 "id": "req_openai_2",
#                 "model": "gpt-4o-mini",
#                 "choices": [{"message": {"content": "```json\n{\"message\":\"hello fenced\"}\n```"}}],
#             }
#         ),
#     )

#     result = OpenAIProvider().generate_json("x", TinySchema)
#     assert result.parsed.message == "hello fenced"


def test_claude_provider_parses_prefixed_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setattr(
        "agentforge.providers.claude_client.httpx.post",
        lambda *args, **kwargs: _FakeResponse(
            {
                "id": "msg_2",
                "model": "claude-3-5-haiku-latest",
                "content": [{"type": "text", "text": "Here is the JSON:\n{\"message\":\"hi prefixed\"}"}],
            }
        ),
    )

    result = ClaudeProvider().generate_json("x", TinySchema)
    assert result.parsed.message == "hi prefixed"


def test_provider_validation_errors_and_missing_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ProviderPermanentError):
        OpenAIProvider().generate_json("x", TinySchema)

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "agentforge.providers.openai_client.httpx.post",
        lambda *args, **kwargs: _FakeResponse(
            {"choices": [{"message": {"content": "not-json"}}], "model": "gpt-4o-mini"}
        ),
    )
    with pytest.raises(ProviderValidationError, match="raw excerpt"):
        OpenAIProvider().generate_json("x", TinySchema)


def test_openai_provider_reports_non_json_for_truncated_top_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr(
        "agentforge.providers.openai_client.httpx.post",
        lambda *args, **kwargs: _FakeResponse(
            {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"generated_at":"2026-01-01T00:00:00Z","items":[{"message":"ok"}'
                            )
                        }
                    }
                ],
                "model": "gpt-4o-mini",
            }
        ),
    )

    with pytest.raises(ProviderValidationError, match="returned non-JSON output"):
        OpenAIProvider().generate_json("x", TinySchema)


# def test_openai_provider_raises_on_truncated_finish_reason(
#     monkeypatch: pytest.MonkeyPatch,
# ) -> None:
#     monkeypatch.setenv("OPENAI_API_KEY", "test-key")
#     monkeypatch.setattr(
#         "agentforge.providers.openai_client.httpx.post",
#         lambda *args, **kwargs: _FakeResponse(
#             {
#                 "choices": [
#                     {
#                         "finish_reason": "length",
#                         "message": {"content": '{"message":"partial"}'},
#                     }
#                 ],
#                 "model": "gpt-4o-mini",
#             }
#         ),
#     )

#     with pytest.raises(ProviderValidationError, match="finish_reason=length"):
#         OpenAIProvider().generate_json("x", TinySchema)
