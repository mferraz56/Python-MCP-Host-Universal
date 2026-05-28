"""Helpers for OpenRouter function schemas and MCP tool dispatch."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any, TypeAlias

from .mcp_runtime import CallToolResultLike, ClientSessionLike, MCPRuntime, MCPToolInfo
from .openrouter import OpenRouterToolCall

JSONDict: TypeAlias = dict[str, Any]


class MCPToolDispatchError(RuntimeError):
    """Report one controlled MCP tool schema or dispatch failure."""


def build_openrouter_tool_schemas(runtime: MCPRuntime) -> list[JSONDict]:
    """Convert connected MCP tools into OpenRouter function tool schemas."""

    schemas: list[JSONDict] = []
    seen_names: set[str] = set()

    for tools in runtime.tools_by_service.values():
        for tool in tools:
            if tool.name in seen_names:
                raise MCPToolDispatchError(f"Duplicate MCP tool name: {tool.name}.")
            seen_names.add(tool.name)
            schemas.append(_build_openrouter_tool_schema(tool))

    return schemas


def resolve_tool_session(runtime: MCPRuntime, tool_name: str) -> tuple[str, ClientSessionLike]:
    """Resolve one normalized tool name to the owning connected service session."""

    matches = [
        service_name
        for service_name, tools in runtime.tools_by_service.items()
        if any(tool.name == tool_name for tool in tools)
    ]
    if not matches:
        raise MCPToolDispatchError(f"Unknown MCP tool: {tool_name}.")
    if len(matches) > 1:
        raise MCPToolDispatchError(f"Ambiguous MCP tool name: {tool_name}.")

    service_name = matches[0]
    session = runtime.sessions.get(service_name)
    if session is None:
        raise MCPToolDispatchError(f"MCP tool is not connected: {tool_name}.")
    return service_name, session


def parse_tool_call_arguments(arguments: str, *, tool_name: str) -> JSONDict:
    """Parse one JSON argument string from an OpenRouter tool call into a dict."""

    cleaned = arguments.strip()
    if not cleaned:
        return {}

    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise MCPToolDispatchError(f"Invalid JSON arguments for tool: {tool_name}.") from exc

    if parsed is None:
        return {}
    if not isinstance(parsed, Mapping):
        raise MCPToolDispatchError(f"Tool arguments must decode to a JSON object: {tool_name}.")
    return dict(parsed)


def normalize_tool_result_text(result: CallToolResultLike) -> str:
    """Extract stable text from one MCP call-tool result."""

    content = getattr(result, "content", ())
    parts = [_normalize_content_block(block) for block in content]
    text_parts = [part for part in parts if part]
    if text_parts:
        return "\n".join(text_parts)

    structured_content = getattr(result, "structuredContent", None)
    if structured_content is None:
        return ""
    return _dump_json_value(structured_content)


async def dispatch_openrouter_tool_call(
    runtime: MCPRuntime,
    tool_call: OpenRouterToolCall,
) -> str:
    """Dispatch one normalized OpenRouter tool call against the owning MCP session."""

    _, session = resolve_tool_session(runtime, tool_call.name)
    arguments = parse_tool_call_arguments(tool_call.arguments, tool_name=tool_call.name)
    result = await session.call_tool(tool_call.name, arguments)
    return normalize_tool_result_text(result)


def _build_openrouter_tool_schema(tool: MCPToolInfo) -> JSONDict:
    function_schema: JSONDict = {
        "name": tool.name,
        "parameters": _normalize_parameters_schema(tool.input_schema),
    }
    if tool.description:
        function_schema["description"] = tool.description

    return {
        "type": "function",
        "function": function_schema,
    }


def _normalize_parameters_schema(input_schema: Mapping[str, Any]) -> JSONDict:
    if input_schema:
        return dict(input_schema)
    return {"type": "object", "properties": {}}


def _normalize_content_block(block: object) -> str | None:
    text = _read_text(block)
    if text is not None:
        return text

    normalized = _normalize_json_value(block)
    if normalized is None:
        return None
    return _dump_json_value(normalized)


def _read_text(value: object) -> str | None:
    if isinstance(value, Mapping):
        text = value.get("text")
    else:
        text = getattr(value, "text", None)
    if isinstance(text, str):
        return text
    return None


def _dump_json_value(value: object) -> str:
    normalized = _normalize_json_value(value)
    if isinstance(normalized, str):
        return normalized
    return json.dumps(normalized, ensure_ascii=True, sort_keys=True)


def _normalize_json_value(value: object) -> object:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Mapping):
        return {str(key): _normalize_json_value(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_json_value(item) for item in value]

    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        return _normalize_json_value(model_dump(mode="json"))

    return str(value)


__all__ = [
    "MCPToolDispatchError",
    "build_openrouter_tool_schemas",
    "dispatch_openrouter_tool_call",
    "normalize_tool_result_text",
    "parse_tool_call_arguments",
    "resolve_tool_session",
]