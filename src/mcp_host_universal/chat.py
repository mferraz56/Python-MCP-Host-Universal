"""Async chat orchestration for OpenRouter tool use and final responses."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from typing import Any, Protocol

from .mcp_runtime import MCPRuntime
from .openrouter import (
    OpenRouterMessage,
    OpenRouterResponse,
    OpenRouterToolCall,
    extract_javascript_code,
)
from .session import (
    HostSessionState,
    SessionMessage,
    SessionToolCall,
    serialize_session_messages,
)
from .tools import (
    MCPToolDispatchError,
    build_openrouter_tool_schemas,
    dispatch_openrouter_tool_call,
)


class ChatCompletionClient(Protocol):
    """Minimal OpenRouter client contract used by the chat orchestration loop."""

    async def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        models: Sequence[str],
        *,
        tools: Sequence[Mapping[str, object]] | None = None,
        use_tools: bool = False,
        max_tokens: int = 8192,
        temperature: float = 0.1,
    ) -> OpenRouterResponse: ...


@dataclass(frozen=True, slots=True)
class ChatEvent:
    """Describe one renderable chat event appended during one user turn."""

    message: SessionMessage
    model: str | None = None
    tool_name: str | None = None
    is_error: bool = False


@dataclass(frozen=True, slots=True)
class ChatTurnResult:
    """Describe the appended events and final renderable outcome for one turn."""

    events: tuple[ChatEvent, ...]
    final_text: str
    extracted_javascript: str | None = None
    final_model: str | None = None
    used_final_model: bool = False


async def run_chat_turn(
    state: HostSessionState,
    runtime: MCPRuntime,
    user_text: str,
    *,
    client: ChatCompletionClient,
    allow_javascript_code_execution: bool = False,
    max_tool_rounds: int = 8,
) -> ChatTurnResult:
    """Append one user turn, execute MCP tools, and return renderable events."""

    events: list[ChatEvent] = []
    final_text = ""
    final_model: str | None = None
    extracted_javascript: str | None = None

    user_message = SessionMessage(role="user", content=user_text)
    _append_event(state, events, user_message)

    tool_schemas = build_openrouter_tool_schemas(runtime) if runtime.tools_by_service else []
    used_tools = False

    if tool_schemas and max_tool_rounds > 0:
        for _ in range(max_tool_rounds):
            response = await client.complete(
                messages=serialize_session_messages(state.messages),
                models=state.config.openrouter.models.tools,
                tools=tool_schemas,
                use_tools=True,
            )

            if response.message.tool_calls:
                assistant_tool_message = _assistant_message_from_response(response.message)
                _append_event(
                    state,
                    events,
                    assistant_tool_message,
                    model=response.model,
                )
                used_tools = True

                for tool_call in response.message.tool_calls:
                    tool_result_text, is_error = await _dispatch_tool_call(runtime, tool_call)
                    tool_message = SessionMessage(
                        role="tool",
                        content=tool_result_text,
                        tool_call_id=tool_call.id,
                    )
                    _append_event(
                        state,
                        events,
                        tool_message,
                        model=response.model,
                        tool_name=tool_call.name,
                        is_error=is_error,
                    )
                break

            if not used_tools and allow_javascript_code_execution:
                extracted_javascript = extract_javascript_code(response.message.content)
                if extracted_javascript is not None:
                    assistant_message = SessionMessage(
                        role="assistant",
                        content=response.message.content,
                    )
                    _append_event(
                        state,
                        events,
                        assistant_message,
                        model=response.model,
                    )
                    synthetic_tool_call = OpenRouterToolCall(
                        id="auto-extract",
                        name="create_workflow_from_code",
                        arguments=json.dumps(
                            {"workflowCode": extracted_javascript},
                            ensure_ascii=False,
                            sort_keys=True,
                        ),
                    )
                    tool_result_text, is_error = await _dispatch_tool_call(runtime, synthetic_tool_call)
                    tool_message = SessionMessage(
                        role="tool",
                        content=tool_result_text,
                        tool_call_id=synthetic_tool_call.id,
                    )
                    _append_event(
                        state,
                        events,
                        tool_message,
                        tool_name=synthetic_tool_call.name,
                        is_error=is_error,
                    )
                    used_tools = True
                    break

            if used_tools:
                break

            assistant_message = SessionMessage(role="assistant", content=response.message.content)
            _append_event(
                state,
                events,
                assistant_message,
                model=response.model,
            )
            final_text = response.message.content
            extracted_javascript = _extract_javascript_if_allowed(
                response.message.content,
                allow_javascript_code_execution,
            )
            return ChatTurnResult(
                events=tuple(events),
                final_text=final_text,
                extracted_javascript=extracted_javascript,
                final_model=response.model,
                used_final_model=False,
            )

    if not used_tools and not tool_schemas:
        final_response = await _complete_final_response(state, client)
        final_message = SessionMessage(role="assistant", content=final_response.message.content)
        _append_event(
            state,
            events,
            final_message,
            model=final_response.model,
        )
        final_text = final_response.message.content
        extracted_javascript = _extract_javascript_if_allowed(
            final_response.message.content,
            allow_javascript_code_execution,
        )
        final_model = final_response.model
        return ChatTurnResult(
            events=tuple(events),
            final_text=final_text,
            extracted_javascript=extracted_javascript,
            final_model=final_model,
            used_final_model=True,
        )

    final_response = await _complete_final_response(state, client)
    final_message = SessionMessage(role="assistant", content=final_response.message.content)
    _append_event(
        state,
        events,
        final_message,
        model=final_response.model,
    )
    final_text = final_response.message.content
    final_model = final_response.model
    if extracted_javascript is None:
        extracted_javascript = _extract_javascript_if_allowed(
            final_response.message.content,
            allow_javascript_code_execution,
        )
    return ChatTurnResult(
        events=tuple(events),
        final_text=final_text,
        extracted_javascript=extracted_javascript,
        final_model=final_model,
        used_final_model=True,
    )


async def _complete_final_response(
    state: HostSessionState,
    client: ChatCompletionClient,
) -> OpenRouterResponse:
    return await client.complete(
        messages=serialize_session_messages(state.messages),
        models=state.config.openrouter.models.final,
        use_tools=False,
    )


async def _dispatch_tool_call(
    runtime: MCPRuntime,
    tool_call: OpenRouterToolCall,
) -> tuple[str, bool]:
    try:
        tool_result_text = await dispatch_openrouter_tool_call(runtime, tool_call)
    except MCPToolDispatchError as exc:
        return _render_tool_error(exc), True
    except Exception as exc:  # pragma: no cover - covered by fake runtime tests.
        return _render_tool_error(exc), True
    if tool_result_text:
        return tool_result_text, False
    return "(no tool output)", False


def _append_event(
    state: HostSessionState,
    events: list[ChatEvent],
    message: SessionMessage,
    *,
    model: str | None = None,
    tool_name: str | None = None,
    is_error: bool = False,
) -> None:
    state.messages.append(message)
    events.append(
        ChatEvent(
            message=message,
            model=model,
            tool_name=tool_name,
            is_error=is_error,
        )
    )


def _assistant_message_from_response(message: OpenRouterMessage) -> SessionMessage:
    return SessionMessage(
        role="assistant",
        content=message.content,
        tool_calls=tuple(
            SessionToolCall(
                id=tool_call.id,
                name=tool_call.name,
                arguments=tool_call.arguments,
            )
            for tool_call in message.tool_calls
        ),
    )


def _extract_javascript_if_allowed(content: str, allow_extraction: bool) -> str | None:
    if not allow_extraction:
        return None
    return extract_javascript_code(content)


def _render_tool_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return f"Error: {message}"
    return "Error: Tool execution failed."


__all__ = [
    "ChatCompletionClient",
    "ChatEvent",
    "ChatTurnResult",
    "run_chat_turn",
]