"""Focused smoke tests for MCP tool schema conversion and dispatch."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

import pytest

from mcp_host_universal.mcp_runtime import MCPRuntime, MCPToolInfo
from mcp_host_universal.openrouter import OpenRouterToolCall
from mcp_host_universal.tools import (
    MCPToolDispatchError,
    build_openrouter_tool_schemas,
    dispatch_openrouter_tool_call,
)


@dataclass(frozen=True, slots=True)
class FakeTextBlock:
    """Provide the text field shape returned by MCP content blocks."""

    text: str


@dataclass(frozen=True, slots=True)
class FakeCallToolResult:
    """Provide the subset of MCP call-tool result fields used by the helper."""

    content: tuple[object, ...]
    structuredContent: object | None = None
    isError: bool | None = False


@dataclass(slots=True)
class FakeSession:
    """Capture dispatched tool calls without real MCP transport."""

    result_text: str
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
        return FakeCallToolResult(content=(FakeTextBlock(self.result_text),))


def test_build_openrouter_tool_schemas_from_runtime() -> None:
    """Connected runtime tools should convert into OpenRouter function schemas."""

    runtime = _build_runtime(
        tools_by_service={
            "weather": (
                MCPToolInfo(
                    name="lookup_weather",
                    description="Fetch the current weather.",
                    input_schema={
                        "type": "object",
                        "properties": {"city": {"type": "string"}},
                        "required": ["city"],
                    },
                ),
            )
        },
        sessions={},
    )

    schemas = build_openrouter_tool_schemas(runtime)

    assert schemas == [
        {
            "type": "function",
            "function": {
                "name": "lookup_weather",
                "description": "Fetch the current weather.",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]


def test_dispatch_openrouter_tool_call_uses_the_matching_session() -> None:
    """Tool dispatch should call only the session that owns the normalized tool name."""

    weather_session = FakeSession("Clear skies over Porto Alegre.")
    filesystem_session = FakeSession("unused")
    runtime = _build_runtime(
        tools_by_service={
            "weather": (
                MCPToolInfo(
                    name="lookup_weather",
                    description="Fetch the current weather.",
                    input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
                ),
            ),
            "filesystem": (
                MCPToolInfo(
                    name="read_file",
                    description="Read one file from disk.",
                    input_schema={"type": "object", "properties": {"path": {"type": "string"}}},
                ),
            ),
        },
        sessions={
            "weather": weather_session,
            "filesystem": filesystem_session,
        },
    )

    output = asyncio.run(
        dispatch_openrouter_tool_call(
            runtime,
            OpenRouterToolCall(
                id="call-1",
                name="lookup_weather",
                arguments='{"city": "Porto Alegre"}',
            ),
        )
    )

    assert output == "Clear skies over Porto Alegre."
    assert weather_session.calls == [("lookup_weather", {"city": "Porto Alegre"})]
    assert filesystem_session.calls == []


def test_dispatch_openrouter_tool_call_rejects_invalid_json_arguments() -> None:
    """Malformed OpenRouter tool arguments should fail with a controlled error."""

    weather_session = FakeSession("unused")
    runtime = _build_runtime(
        tools_by_service={
            "weather": (
                MCPToolInfo(
                    name="lookup_weather",
                    description="Fetch the current weather.",
                    input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
                ),
            )
        },
        sessions={"weather": weather_session},
    )

    with pytest.raises(MCPToolDispatchError, match="Invalid JSON arguments"):
        asyncio.run(
            dispatch_openrouter_tool_call(
                runtime,
                OpenRouterToolCall(
                    id="call-2",
                    name="lookup_weather",
                    arguments='{"city": ',
                ),
            )
        )

    assert weather_session.calls == []


def test_dispatch_openrouter_tool_call_rejects_unknown_tool_names() -> None:
    """Unknown tool names should fail before dispatching any MCP call."""

    weather_session = FakeSession("unused")
    runtime = _build_runtime(
        tools_by_service={
            "weather": (
                MCPToolInfo(
                    name="lookup_weather",
                    description="Fetch the current weather.",
                    input_schema={"type": "object", "properties": {"city": {"type": "string"}}},
                ),
            )
        },
        sessions={"weather": weather_session},
    )

    with pytest.raises(MCPToolDispatchError, match="Unknown MCP tool"):
        asyncio.run(
            dispatch_openrouter_tool_call(
                runtime,
                OpenRouterToolCall(
                    id="call-3",
                    name="unknown_tool",
                    arguments="{}",
                ),
            )
        )

    assert weather_session.calls == []


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