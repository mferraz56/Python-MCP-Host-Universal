"""Runtime helpers for connecting configured MCP services and caching tool metadata."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, AsyncContextManager, Protocol, TypeAlias

import httpx
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client
from mcp.client.streamable_http import streamable_http_client

from .config import ServiceConfig
from .templates import ServiceTransport

SchemaDict: TypeAlias = dict[str, Any]
TransportPair: TypeAlias = tuple[object, object]
SessionFactory: TypeAlias = Callable[[object, object], AsyncContextManager["ClientSessionLike"]]
HTTPClientFactory: TypeAlias = Callable[..., AsyncContextManager[object]]
HTTPTransportFactory: TypeAlias = Callable[..., AsyncContextManager[tuple[object, object, object]]]
StdioTransportFactory: TypeAlias = Callable[[StdioServerParameters], AsyncContextManager[tuple[object, object]]]


class ListToolsResultLike(Protocol):
    """Minimal list-tools response contract used by the runtime."""

    tools: Sequence[object]
    nextCursor: str | None


class CallToolResultLike(Protocol):
    """Minimal call-tool response contract used by tool dispatch helpers."""

    content: Sequence[object]
    structuredContent: object | None
    isError: bool | None


class ClientSessionLike(Protocol):
    """Minimal client session contract needed for initialization, discovery, and calls."""

    async def initialize(self) -> object:
        """Initialize the client session against the remote MCP service."""

    async def list_tools(
        self,
        cursor: str | None = None,
        *,
        params: object = None,
    ) -> ListToolsResultLike:
        """Return one page of tools from the connected MCP service."""

    async def call_tool(
        self,
        name: str,
        arguments: dict[str, Any] | None = None,
        **kwargs: object,
    ) -> CallToolResultLike:
        """Call one remote MCP tool by name."""


@dataclass(frozen=True, slots=True)
class MCPToolInfo:
    """Store one normalized tool definition exposed by a connected service."""

    name: str
    description: str | None
    input_schema: SchemaDict
    output_schema: SchemaDict | None = None


@dataclass(frozen=True, slots=True)
class MCPServiceConnectionResult:
    """Store one service connection outcome and its normalized tool catalog."""

    service_name: str
    transport: str
    ok: bool
    tools: tuple[MCPToolInfo, ...] = ()
    system_prompt: str = ""
    error: str | None = None


@dataclass(slots=True)
class _ConnectedService:
    """Keep one live session and its transport stack attached to the runtime."""

    service_name: str
    session: ClientSessionLike
    exit_stack: AsyncExitStack


@dataclass(slots=True)
class MCPRuntime:
    """Keep connected MCP sessions alive until the host is ready to shut down."""

    results: tuple[MCPServiceConnectionResult, ...]
    tools_by_service: dict[str, tuple[MCPToolInfo, ...]]
    system_prompts: dict[str, str]
    _sessions: dict[str, ClientSessionLike] = field(repr=False, default_factory=dict)
    _exit_stack: AsyncExitStack = field(repr=False, default_factory=AsyncExitStack)
    _closed: bool = field(init=False, default=False, repr=False)

    @property
    def sessions(self) -> Mapping[str, ClientSessionLike]:
        """Return the successful live sessions keyed by normalized service name."""

        return dict(self._sessions)

    async def close(self) -> None:
        """Close all successful sessions and transports once."""

        if self._closed:
            return
        self._closed = True
        await self._exit_stack.aclose()

    async def __aenter__(self) -> MCPRuntime:
        """Return the runtime so callers can use `async with` if preferred."""

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the runtime when leaving an async context manager block."""

        del exc_type, exc, traceback
        await self.close()


async def connect_mcp_services(
    services: Sequence[ServiceConfig],
    *,
    session_factory: SessionFactory = ClientSession,
    stdio_transport_factory: StdioTransportFactory = stdio_client,
    http_transport_factory: HTTPTransportFactory = streamable_http_client,
    http_client_factory: HTTPClientFactory = httpx.AsyncClient,
) -> MCPRuntime:
    """Connect enabled MCP services and keep successful sessions available for later use."""

    runtime_stack = AsyncExitStack()
    results: list[MCPServiceConnectionResult] = []
    tools_by_service: dict[str, tuple[MCPToolInfo, ...]] = {}
    system_prompts: dict[str, str] = {}
    sessions: dict[str, ClientSessionLike] = {}
    name_counts: dict[str, int] = {}

    try:
        for index, service in enumerate(services, start=1):
            service_name = _resolve_service_name(service, index, name_counts)
            result, connected = await _connect_service(
                service_name,
                service,
                session_factory=session_factory,
                stdio_transport_factory=stdio_transport_factory,
                http_transport_factory=http_transport_factory,
                http_client_factory=http_client_factory,
            )
            results.append(result)
            if connected is None:
                continue

            await runtime_stack.enter_async_context(connected.exit_stack)
            sessions[service_name] = connected.session
            tools_by_service[service_name] = result.tools
            system_prompts[service_name] = result.system_prompt

        return MCPRuntime(
            results=tuple(results),
            tools_by_service=tools_by_service,
            system_prompts=system_prompts,
            _sessions=sessions,
            _exit_stack=runtime_stack,
        )
    except Exception:
        await runtime_stack.aclose()
        raise


async def _connect_service(
    service_name: str,
    service: ServiceConfig,
    *,
    session_factory: SessionFactory,
    stdio_transport_factory: StdioTransportFactory,
    http_transport_factory: HTTPTransportFactory,
    http_client_factory: HTTPClientFactory,
) -> tuple[MCPServiceConnectionResult, _ConnectedService | None]:
    transport = _normalize_transport(service.transport)
    system_prompt = service.system_prompt.strip()

    if not service.enabled:
        return (
            MCPServiceConnectionResult(
                service_name=service_name,
                transport=transport,
                ok=False,
                system_prompt=system_prompt,
                error="Service disabled.",
            ),
            None,
        )

    service_stack = AsyncExitStack()
    try:
        read_stream, write_stream = await _open_transport(
            service,
            service_stack,
            stdio_transport_factory=stdio_transport_factory,
            http_transport_factory=http_transport_factory,
            http_client_factory=http_client_factory,
        )
        session = await service_stack.enter_async_context(session_factory(read_stream, write_stream))
        await session.initialize()
        tools = await _list_all_tools(session)
    except Exception as exc:
        await service_stack.aclose()
        return (
            MCPServiceConnectionResult(
                service_name=service_name,
                transport=transport,
                ok=False,
                system_prompt=system_prompt,
                error=_format_service_error(service, exc),
            ),
            None,
        )

    return (
        MCPServiceConnectionResult(
            service_name=service_name,
            transport=transport,
            ok=True,
            tools=tools,
            system_prompt=system_prompt,
        ),
        _ConnectedService(
            service_name=service_name,
            session=session,
            exit_stack=service_stack,
        ),
    )


async def _open_transport(
    service: ServiceConfig,
    service_stack: AsyncExitStack,
    *,
    stdio_transport_factory: StdioTransportFactory,
    http_transport_factory: HTTPTransportFactory,
    http_client_factory: HTTPClientFactory,
) -> TransportPair:
    transport = _normalize_transport(service.transport)

    if transport == ServiceTransport.HTTP.value:
        url = _require_text(service.url, "HTTP service requires a url.")
        headers = _build_http_headers(service.token)
        http_client = await service_stack.enter_async_context(http_client_factory(headers=headers or None))
        read_stream, write_stream, _ = await service_stack.enter_async_context(
            http_transport_factory(
                url,
                http_client=http_client,
                terminate_on_close=True,
            )
        )
        return read_stream, write_stream

    if transport == ServiceTransport.STDIO.value:
        command = _require_text(service.command, "stdio service requires a command.")
        read_stream, write_stream = await service_stack.enter_async_context(
            stdio_transport_factory(
                StdioServerParameters(
                    command=command,
                    args=list(service.args),
                    env=dict(service.env) or None,
                    cwd=_service_cwd(service),
                )
            )
        )
        return read_stream, write_stream

    raise ValueError(f"Unsupported transport: {transport or '<empty>'}.")


async def _list_all_tools(session: ClientSessionLike) -> tuple[MCPToolInfo, ...]:
    tools: list[MCPToolInfo] = []
    cursor: str | None = None
    seen_cursors: set[str] = set()

    while True:
        page = await session.list_tools(cursor)
        tools.extend(_normalize_tool(tool) for tool in page.tools)

        next_cursor = getattr(page, "nextCursor", None)
        if not isinstance(next_cursor, str) or not next_cursor:
            return tuple(tools)
        if next_cursor in seen_cursors:
            raise RuntimeError("Tool listing returned a repeated cursor.")

        seen_cursors.add(next_cursor)
        cursor = next_cursor


def _normalize_tool(tool: object) -> MCPToolInfo:
    return MCPToolInfo(
        name=_read_string(tool, "name"),
        description=_optional_string(_read_field(tool, "description")),
        input_schema=_mapping_copy(_read_field(tool, "inputSchema")) or {},
        output_schema=_mapping_copy(_read_field(tool, "outputSchema")),
    )


def _resolve_service_name(
    service: ServiceConfig,
    index: int,
    name_counts: dict[str, int],
) -> str:
    base_name = service.name.strip() or f"service-{index}"
    count = name_counts.get(base_name, 0) + 1
    name_counts[base_name] = count
    return base_name if count == 1 else f"{base_name}-{count}"


def _normalize_transport(transport: str) -> str:
    return transport.strip().lower()


def _build_http_headers(token: str | None) -> dict[str, str] | None:
    cleaned = token.strip() if isinstance(token, str) else ""
    if not cleaned:
        return None
    return {"Authorization": f"Bearer {cleaned}"}


def _service_cwd(service: ServiceConfig) -> str | None:
    cwd = service.extra.get("cwd")
    if isinstance(cwd, str) and cwd.strip():
        return cwd.strip()
    return None


def _require_text(value: str | None, message: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(message)
    return value.strip()


def _format_service_error(service: ServiceConfig, exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    token = service.token.strip() if isinstance(service.token, str) else ""
    if token:
        message = message.replace(f"Bearer {token}", "Bearer [redacted]")
        message = message.replace(token, "[redacted]")
    if len(message) > 240:
        return f"{message[:237].rstrip()}..."
    return message


def _read_field(value: object, field_name: str) -> object:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _read_string(value: object, field_name: str) -> str:
    field_value = _read_field(value, field_name)
    if isinstance(field_value, str):
        return field_value.strip()
    return ""


def _optional_string(value: object) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    return None


def _mapping_copy(value: object) -> SchemaDict | None:
    if not isinstance(value, Mapping):
        return None
    return dict(value)


__all__ = [
    "MCPRuntime",
    "MCPServiceConnectionResult",
    "MCPToolInfo",
    "connect_mcp_services",
]