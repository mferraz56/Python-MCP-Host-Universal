"""Focused tests for the async OpenRouter client fallback behavior."""

from __future__ import annotations

import asyncio

import pytest

from mcp_host_universal.openrouter import (
    OpenRouterClient,
    OpenRouterError,
    OpenRouterHTTPResponse,
    OpenRouterRequest,
    OpenRouterToolCall,
    build_openrouter_payload,
    content_has_tool_text_marker,
    extract_javascript_code,
)


class ScriptedRequester:
    """Replay canned responses for each requested model."""

    def __init__(self, scripted: dict[str, list[object]]) -> None:
        self._scripted = {model: list(items) for model, items in scripted.items()}
        self.calls: list[OpenRouterRequest] = []

    async def __call__(self, openrouter_request: OpenRouterRequest) -> OpenRouterHTTPResponse:
        self.calls.append(openrouter_request)
        responses = self._scripted[openrouter_request.model]
        response = responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        assert isinstance(response, OpenRouterHTTPResponse)
        return response


class SleepRecorder:
    """Record retry delays without waiting in tests."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


def test_complete_retries_429_then_falls_back_to_next_model() -> None:
    """The client should retry one model before using the next configured fallback."""

    requester = ScriptedRequester(
        {
            "tool-model": [
                OpenRouterHTTPResponse(
                    status_code=429,
                    text_body='{"error":{"message":"Authorization: Bearer sk-secret"}}',
                ),
                OpenRouterHTTPResponse(
                    status_code=429,
                    text_body='{"error":{"message":"Authorization: Bearer sk-secret"}}',
                ),
                OpenRouterHTTPResponse(
                    status_code=429,
                    text_body='{"error":{"message":"Authorization: Bearer sk-secret"}}',
                ),
            ],
            "backup-model": [
                OpenRouterHTTPResponse(
                    status_code=200,
                    json_body={
                        "model": "backup-model",
                        "choices": [
                            {
                                "finish_reason": "tool_calls",
                                "message": {
                                    "role": "assistant",
                                    "content": "Done.",
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "function": {
                                                "name": "lookup_weather",
                                                "arguments": '{"city": "Sao Paulo"}',
                                            },
                                        }
                                    ],
                                },
                            }
                        ],
                    },
                )
            ],
        }
    )
    sleeper = SleepRecorder()
    tools = [
        {
            "type": "function",
            "function": {
                "name": "lookup_weather",
                "description": "Fetch the current weather.",
                "parameters": {"type": "object", "properties": {"city": {"type": "string"}}},
            },
        }
    ]
    client = OpenRouterClient(
        "sk-secret",
        requester=requester,
        sleep=sleeper,
        max_attempts=3,
    )

    response = asyncio.run(
        client.complete(
            messages=[{"role": "user", "content": "Qual o clima?"}],
            models=["tool-model", "backup-model"],
            tools=tools,
            use_tools=True,
        )
    )

    assert response.model == "backup-model"
    assert response.message.content == "Done."
    assert response.message.tool_calls == (
        OpenRouterToolCall(
            id="call_1",
            name="lookup_weather",
            arguments='{"city": "Sao Paulo"}',
        ),
    )
    assert [call.model for call in requester.calls] == [
        "tool-model",
        "tool-model",
        "tool-model",
        "backup-model",
    ]
    assert sleeper.delays == [10.0, 20.0, 30.0]
    assert requester.calls[0].payload["tool_choice"] == "auto"
    assert requester.calls[0].payload["tools"] == tools


def test_complete_skips_textual_tool_calls_and_uses_next_model() -> None:
    """Tool-use text markers should force a fallback when tool calls are required."""

    requester = ScriptedRequester(
        {
            "tool-model": [
                OpenRouterHTTPResponse(
                    status_code=200,
                    json_body={
                        "model": "tool-model",
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": '<tool_call>{"function":"lookup_weather"}</tool_call>',
                                }
                            }
                        ],
                    },
                )
            ],
            "backup-model": [
                OpenRouterHTTPResponse(
                    status_code=200,
                    json_body={
                        "model": "backup-model",
                        "choices": [
                            {
                                "message": {
                                    "role": "assistant",
                                    "content": "Ready.",
                                    "tool_calls": [
                                        {
                                            "id": "call_2",
                                            "function": {
                                                "name": "lookup_weather",
                                                "arguments": '{"city":"Recife"}',
                                            },
                                        }
                                    ],
                                }
                            }
                        ],
                    },
                )
            ],
        }
    )
    client = OpenRouterClient(
        "sk-secret",
        requester=requester,
        sleep=SleepRecorder(),
        max_attempts=1,
    )

    response = asyncio.run(
        client.complete(
            messages=[{"role": "user", "content": "Use a ferramenta."}],
            models=["tool-model", "backup-model"],
            tools=[{"type": "function", "function": {"name": "lookup_weather"}}],
            use_tools=True,
        )
    )

    assert response.model == "backup-model"
    assert [call.model for call in requester.calls] == ["tool-model", "backup-model"]


def test_build_payload_and_text_detectors_match_js_contract() -> None:
    """The payload and text heuristics should follow the legacy JavaScript behavior."""

    payload = build_openrouter_payload(
        "tool-model",
        [{"role": "user", "content": "hello"}],
        tools=[{"type": "function", "function": {"name": "lookup_weather"}}],
        use_tools=True,
    )
    plain_payload = build_openrouter_payload(
        "plain-model",
        [{"role": "user", "content": "hello"}],
        tools=[{"type": "function", "function": {"name": "lookup_weather"}}],
        use_tools=False,
    )

    assert payload["tool_choice"] == "auto"
    assert "tools" in payload
    assert "tool_choice" not in plain_payload
    assert "tools" not in plain_payload
    assert content_has_tool_text_marker('"function": {"name": "lookup_weather"}') is True
    assert content_has_tool_text_marker("normal text") is False
    assert extract_javascript_code("```javascript\nexport default { ok: true };\n```") == (
        "export default { ok: true };"
    )
    assert extract_javascript_code("before export default run();") == "export default run();"


def test_complete_raises_short_safe_errors_without_api_key_leakage() -> None:
    """Failures should stay short and never echo credentials back to the caller."""

    requester = ScriptedRequester(
        {
            "broken-model": [
                RuntimeError(
                    "500 Authorization: Bearer sk-secret failed with token sk-secret and a very long "
                    "message that should be collapsed before it reaches the caller."
                )
            ]
        }
    )
    client = OpenRouterClient(
        "sk-secret",
        requester=requester,
        sleep=SleepRecorder(),
        max_attempts=1,
    )

    with pytest.raises(OpenRouterError) as excinfo:
        asyncio.run(
            client.complete(
                messages=[{"role": "user", "content": "hello"}],
                models=["broken-model"],
            )
        )

    message = str(excinfo.value)
    assert message == "OpenRouter request failed."
    assert "Authorization" not in message
    assert "Bearer" not in message
    assert "sk-secret" not in message
    assert len(message) <= 120