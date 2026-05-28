"""Typed interactive session state for slash-command routing and chat history."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, TypeAlias

from .config import HostConfig, PathLike, ServiceConfig
from .mcp_runtime import MCPServiceConnectionResult, MCPToolInfo
from .ui.render import DEFAULT_HELP_COMMANDS

MessageRole: TypeAlias = Literal["system", "user", "assistant", "tool"]
HelpCommand: TypeAlias = tuple[str, str]


@dataclass(frozen=True, slots=True)
class SessionToolCall:
    """Store one assistant tool call in a replayable OpenRouter-friendly shape."""

    id: str
    name: str
    arguments: str

    def to_openrouter_mapping(self) -> dict[str, object]:
        """Render one stored tool call into the OpenRouter chat payload shape."""

        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments,
            },
        }


@dataclass(frozen=True, slots=True)
class SessionMessage:
    """Store one transcript entry with optional tool metadata for replay."""

    role: MessageRole
    content: str
    tool_calls: tuple[SessionToolCall, ...] = ()
    tool_call_id: str | None = None

    def to_openrouter_mapping(self) -> dict[str, object]:
        """Render one transcript entry into the OpenRouter message shape."""

        payload: dict[str, object] = {
            "role": self.role,
            "content": self.content,
        }
        if self.role == "assistant" and self.tool_calls:
            payload["tool_calls"] = [
                tool_call.to_openrouter_mapping() for tool_call in self.tool_calls
            ]
        if self.role == "tool" and self.tool_call_id is not None:
            payload["tool_call_id"] = self.tool_call_id
        return payload


def serialize_session_messages(messages: Sequence[SessionMessage]) -> list[dict[str, Any]]:
    """Convert stored session messages into OpenRouter-compatible payload dicts."""

    return [message.to_openrouter_mapping() for message in messages]


@dataclass(slots=True)
class HostSessionState:
    """Keep the mutable config and transcript used by slash commands."""

    config: HostConfig
    messages: list[SessionMessage] = field(default_factory=list)
    connection_results: tuple[MCPServiceConnectionResult, ...] = ()
    tools_by_service: dict[str, tuple[MCPToolInfo, ...]] = field(default_factory=dict)
    help_commands: tuple[HelpCommand, ...] = DEFAULT_HELP_COMMANDS
    config_path: PathLike | None = None

    def clear_history(self) -> None:
        """Keep only the first system message when clearing the transcript."""

        if not self.messages:
            return

        first_message = self.messages[0]
        if first_message.role == "system":
            self.messages[:] = [first_message]
            return

        self.messages.clear()

    def set_active_model(self, model_id: str) -> None:
        """Update both tool and final model selections to one model id."""

        self.config.openrouter.models.tools = [model_id]
        self.config.openrouter.models.final = [model_id]

    def append_service(self, service: ServiceConfig) -> None:
        """Append one configured MCP service to the in-memory config."""

        self.config.services.append(service)

    def replace_services(self, services: Sequence[ServiceConfig]) -> None:
        """Replace the configured MCP service list in place."""

        self.config.services[:] = list(services)

    def configured_services(self) -> tuple[ServiceConfig, ...]:
        """Expose the configured services as an immutable snapshot."""

        return tuple(self.config.services)


__all__ = [
    "HelpCommand",
    "HostSessionState",
    "MessageRole",
    "SessionMessage",
    "SessionToolCall",
    "serialize_session_messages",
]