"""Focused smoke tests for the async chat orchestration loop."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from mcp_host_universal.chat import run_chat_turn
from mcp_host_universal.config import HostConfig, OpenRouterConfig, OpenRouterModelSelection
from mcp_host_universal.mcp_runtime import MCPRuntime, MCPToolInfo
from mcp_host_universal.openrouter import OpenRouterMessage, OpenRouterResponse, OpenRouterToolCall
from mcp_host_universal.session import HostSessionState, SessionMessage


@dataclass(frozen=True, slots=True)
class FakeTextBlock:
    """Provide the text field shape returned by MCP content blocks."""

    text: str


@dataclass(frozen=True, slots=True)
class FakeCallToolResult:
    """Provide the subset of MCP call-tool result fields used by chat orchestration."""

    content: tuple[object, ...]
    structuredContent: object | None = None
    isError: bool | None = False


@dataclass(slots=True)
class FakeSession:
    """Capture MCP tool dispatches without real transport."""

    result_text: str = ""
    raise_error: Exception | None = None
    calls: list[tuple[str, dict[str, object] | None]] = field(default_factory=list)

    async def initialize(self) -> object:
        raise AssertionError("Unexpected initialize call.")

    async def list_tools(
        self,
        cursor: str | None = None,
        *,
        params: object = None,
    ) -> object:
        del cursor, params
        raise AssertionError("Unexpected list_tools call.")

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, object] | None = None,
        **kwargs: object,
    ) -> FakeCallToolResult:
        del kwargs
        self.calls.append((name, dict(arguments) if arguments is not None else None))
        if self.raise_error is not None:
            raise self.raise_error
        return FakeCallToolResult(content=(FakeTextBlock(self.result_text),))


@dataclass(frozen=True, slots=True)
class ScriptedCompletion:
    """Describe one expected OpenRouter completion request and canned response."""

    models: tuple[str, ...]
    use_tools: bool
    tool_names: tuple[str, ...]
    response: OpenRouterResponse


class ScriptedClient:
    """Replay deterministic OpenRouter responses and capture request payloads."""

    def __init__(self, scripted: list[ScriptedCompletion]) -> None:
        self._scripted = list(scripted)
        self.calls: list[dict[str, object]] = []

    async def complete(
        self,
        messages: list[dict[str, object]],
        models: list[str],
        *,
        tools: list[dict[str, object]] | None = None,
        use_tools: bool = False,
        max_tokens: int = 8192,
        temperature: float = 0.1,
    ) -> OpenRouterResponse:
        del max_tokens, temperature
        call = {
            "messages": [dict(message) for message in messages],
            "models": tuple(models),
            "use_tools": use_tools,
            "tool_names": tuple(
                str(tool["function"]["name"])
                for tool in tools or ()
                if isinstance(tool, dict)
            ),
        }
        self.calls.append(call)
        scripted = self._scripted.pop(0)
        assert call["models"] == scripted.models
        assert call["use_tools"] is scripted.use_tools
        assert call["tool_names"] == scripted.tool_names
        return scripted.response


def test_run_chat_turn_replays_tool_history_and_finishes_with_final_model() -> None:
    """One tool-planning round should append tool metadata and then use the final model."""

    runtime = _build_runtime(
        tools_by_service={
            "weather": (
                MCPToolInfo(
                    name="lookup_weather",
                    description="Fetch the weather.",
                    input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
                ),
            )
        },
        sessions={"weather": FakeSession("Clear skies over Porto Alegre.")},
    )
    state = _build_state()
    client = ScriptedClient(
        [
            ScriptedCompletion(
                models=("tool-model",),
                use_tools=True,
                tool_names=("lookup_weather",),
                response=OpenRouterResponse(
                    model="tool-model",
                    message=OpenRouterMessage(
                        role="assistant",
                        content="",
                        tool_calls=(
                            OpenRouterToolCall(
                                id="call-1",
                                name="lookup_weather",
                                arguments='{"city": "Porto Alegre"}',
                            ),
                        ),
                    ),
                ),
            ),
            ScriptedCompletion(
                models=("final-model",),
                use_tools=False,
                tool_names=(),
                response=OpenRouterResponse(
                    model="final-model",
                    message=OpenRouterMessage(
                        role="assistant",
                        content="Clear skies in Porto Alegre.",
                    ),
                ),
            ),
        ]
    )

    result = asyncio.run(
        run_chat_turn(
            state,
            runtime,
            "Qual o clima em Porto Alegre?",
            client=client,
        )
    )

    assert result.final_text == "Clear skies in Porto Alegre."
    assert result.final_model == "final-model"
    assert result.used_final_model is True
    assert [event.message.role for event in result.events] == ["user", "assistant", "tool", "assistant"]
    assert state.messages[1].tool_calls[0].name == "lookup_weather"
    assert state.messages[2].tool_call_id == "call-1"
    assert state.messages[3] == SessionMessage(role="assistant", content="Clear skies in Porto Alegre.")
    assert client.calls[1]["messages"] == [
        {"role": "user", "content": "Qual o clima em Porto Alegre?"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "call-1",
                    "type": "function",
                    "function": {
                        "name": "lookup_weather",
                        "arguments": '{"city": "Porto Alegre"}',
                    },
                }
            ],
        },
        {
            "role": "tool",
            "content": "Clear skies over Porto Alegre.",
            "tool_call_id": "call-1",
        },
    ]


def test_run_chat_turn_converts_tool_failures_into_tool_messages() -> None:
    """Invalid JSON, unknown tools, and execution errors should not crash the turn."""

    cases = [
        (
            OpenRouterToolCall(id="call-invalid", name="lookup_weather", arguments='{"city": '),
            _build_runtime(
                tools_by_service={
                    "weather": (
                        MCPToolInfo(
                            name="lookup_weather",
                            description="Fetch the weather.",
                            input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
                        ),
                    )
                },
                sessions={"weather": FakeSession("unused")},
            ),
            "Error: Invalid JSON arguments for tool: lookup_weather.",
        ),
        (
            OpenRouterToolCall(id="call-unknown", name="unknown_tool", arguments="{}"),
            _build_runtime(
                tools_by_service={
                    "weather": (
                        MCPToolInfo(
                            name="lookup_weather",
                            description="Fetch the weather.",
                            input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
                        ),
                    )
                },
                sessions={"weather": FakeSession("unused")},
            ),
            "Error: Unknown MCP tool: unknown_tool.",
        ),
        (
            OpenRouterToolCall(id="call-error", name="lookup_weather", arguments='{"city": "Porto Alegre"}'),
            _build_runtime(
                tools_by_service={
                    "weather": (
                        MCPToolInfo(
                            name="lookup_weather",
                            description="Fetch the weather.",
                            input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
                        ),
                    )
                },
                sessions={"weather": FakeSession(raise_error=RuntimeError("weather backend offline"))},
            ),
            "Error: weather backend offline",
        ),
    ]

    for tool_call, runtime, expected_error in cases:
        state = _build_state()
        client = ScriptedClient(
            [
                ScriptedCompletion(
                    models=("tool-model",),
                    use_tools=True,
                    tool_names=tuple(tool.name for tool in runtime.tools_by_service["weather"]),
                    response=OpenRouterResponse(
                        model="tool-model",
                        message=OpenRouterMessage(
                            role="assistant",
                            content="",
                            tool_calls=(tool_call,),
                        ),
                    ),
                ),
                ScriptedCompletion(
                    models=("final-model",),
                    use_tools=False,
                    tool_names=(),
                    response=OpenRouterResponse(
                        model="final-model",
                        message=OpenRouterMessage(
                            role="assistant",
                            content="Recovered final answer.",
                        ),
                    ),
                ),
            ]
        )

        result = asyncio.run(
            run_chat_turn(
                state,
                runtime,
                "Use a ferramenta.",
                client=client,
            )
        )

        assert result.final_text == "Recovered final answer."
        assert result.events[2].message.role == "tool"
        assert result.events[2].is_error is True
        assert result.events[2].message.content == expected_error


def test_run_chat_turn_does_not_auto_execute_extracted_javascript_by_default() -> None:
    """JavaScript-looking assistant text should stay a normal final answer by default."""

    runtime = _build_runtime(
        tools_by_service={
            "workflow": (
                MCPToolInfo(
                    name="create_workflow_from_code",
                    description="Create a workflow from JavaScript.",
                    input_schema={
                        "type": "object",
                        "properties": {"workflowCode": {"type": "string"}},
                        "required": ["workflowCode"],
                    },
                ),
            )
        },
        sessions={"workflow": FakeSession("workflow created")},
    )
    state = _build_state()
    client = ScriptedClient(
        [
            ScriptedCompletion(
                models=("tool-model",),
                use_tools=True,
                tool_names=("create_workflow_from_code",),
                response=OpenRouterResponse(
                    model="tool-model",
                    message=OpenRouterMessage(
                        role="assistant",
                        content="```javascript\nexport default { ok: true };\n```",
                    ),
                ),
            )
        ]
    )

    result = asyncio.run(
        run_chat_turn(
            state,
            runtime,
            "Monte um workflow.",
            client=client,
        )
    )

    assert result.final_text == "```javascript\nexport default { ok: true };\n```"
    assert result.extracted_javascript is None
    assert state.messages == [
        SessionMessage(role="user", content="Monte um workflow."),
        SessionMessage(
            role="assistant",
            content="```javascript\nexport default { ok: true };\n```",
        ),
    ]
    assert runtime.sessions["workflow"].calls == []


def test_run_chat_turn_can_opt_in_to_javascript_extraction_and_final_fallback() -> None:
    """Opted-in JavaScript extraction should dispatch the synthetic tool and then finalize."""

    runtime = _build_runtime(
        tools_by_service={
            "workflow": (
                MCPToolInfo(
                    name="create_workflow_from_code",
                    description="Create a workflow from JavaScript.",
                    input_schema={
                        "type": "object",
                        "properties": {"workflowCode": {"type": "string"}},
                        "required": ["workflowCode"],
                    },
                ),
            )
        },
        sessions={"workflow": FakeSession("Workflow created from code.")},
    )
    state = _build_state()
    client = ScriptedClient(
        [
            ScriptedCompletion(
                models=("tool-model",),
                use_tools=True,
                tool_names=("create_workflow_from_code",),
                response=OpenRouterResponse(
                    model="tool-model",
                    message=OpenRouterMessage(
                        role="assistant",
                        content="```javascript\nexport default { ok: true };\n```",
                    ),
                ),
            ),
            ScriptedCompletion(
                models=("final-model",),
                use_tools=False,
                tool_names=(),
                response=OpenRouterResponse(
                    model="final-model",
                    message=OpenRouterMessage(
                        role="assistant",
                        content="Workflow created successfully.",
                    ),
                ),
            ),
        ]
    )

    result = asyncio.run(
        run_chat_turn(
            state,
            runtime,
            "Monte um workflow.",
            client=client,
            allow_javascript_code_execution=True,
        )
    )

    assert result.final_text == "Workflow created successfully."
    assert result.extracted_javascript == "export default { ok: true };"
    assert result.used_final_model is True
    assert [event.message.role for event in result.events] == ["user", "assistant", "tool", "assistant"]
    assert runtime.sessions["workflow"].calls == [
        (
            "create_workflow_from_code",
            {"workflowCode": "export default { ok: true };"},
        )
    ]


def _build_state() -> HostSessionState:
    return HostSessionState(
        config=HostConfig(
            openrouter=OpenRouterConfig(
                api_key="sk-test",
                models=OpenRouterModelSelection(
                    tools=["tool-model"],
                    final=["final-model"],
                ),
            )
        ),
        messages=[],
    )


def _build_runtime(
    *,
    tools_by_service: dict[str, tuple[MCPToolInfo, ...]],
    sessions: dict[str, FakeSession],
) -> MCPRuntime:
    return MCPRuntime(
        results=(),
        tools_by_service=tools_by_service,
        system_prompts={},
        _sessions=sessions,
    )