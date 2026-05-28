"""Focused smoke tests for the MCP service runtime slice."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from mcp_host_universal.config import ServiceConfig
from mcp_host_universal.mcp_runtime import connect_mcp_services
from mcp_host_universal.templates import ServiceTransport


@dataclass(frozen=True, slots=True)
class FakeTool:
    """Mimic the SDK tool object shape used by the runtime."""

    name: str
    description: str | None
    inputSchema: dict[str, object]
    outputSchema: dict[str, object] | None = None


@dataclass(frozen=True, slots=True)
class FakeListToolsResult:
    """Mimic the SDK paginated list-tools response."""

    tools: list[FakeTool]
    nextCursor: str | None = None


@dataclass(frozen=True, slots=True)
class FakeReadStream:
    """Carry the service identity from the fake transport into the fake session."""

    service_name: str


@dataclass(frozen=True, slots=True)
class FakeHTTPClient:
    """Store HTTP headers passed into the fake streamable HTTP transport."""

    headers: dict[str, str] | None


@dataclass(slots=True)
class FakeServiceScript:
    """Describe one fake service session for focused runtime coverage."""

    list_tools_pages: list[FakeListToolsResult] = field(default_factory=list)
    initialize_error: Exception | None = None
    list_tools_calls: list[str | None] = field(default_factory=list)


class FakeAsyncContext:
    """Wrap a value in an async context manager and record enter and exit events."""

    def __init__(self, value: object, label: str, events: list[str]) -> None:
        self._value = value
        self._label = label
        self._events = events

    async def __aenter__(self) -> object:
        self._events.append(f"enter:{self._label}")
        return self._value

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        del exc_type, exc, traceback
        self._events.append(f"exit:{self._label}")


class FakeSession:
    """Replay initialization and list-tools behavior without real MCP I/O."""

    def __init__(
        self,
        service_name: str,
        script: FakeServiceScript,
        events: list[str],
    ) -> None:
        self._service_name = service_name
        self._script = script
        self._events = events

    async def initialize(self) -> object:
        self._events.append(f"initialize:{self._service_name}")
        if self._script.initialize_error is not None:
            raise self._script.initialize_error
        return object()

    async def list_tools(
        self,
        cursor: str | None = None,
        *,
        params: object = None,
    ) -> FakeListToolsResult:
        del params
        self._script.list_tools_calls.append(cursor)
        self._events.append(f"list-tools:{self._service_name}:{cursor or '<none>'}")
        if not self._script.list_tools_pages:
            raise AssertionError("Unexpected list_tools call.")
        return self._script.list_tools_pages.pop(0)


class FakeRuntimeHarness:
    """Provide fake SDK factories for the runtime smoke test."""

    def __init__(self, scripts: dict[str, FakeServiceScript]) -> None:
        self._scripts = scripts
        self.events: list[str] = []
        self.http_headers: list[dict[str, str] | None] = []
        self.url_to_service: dict[str, str] = {}
        self.command_to_service: dict[str, str] = {}

    def http_client_factory(
        self,
        *,
        headers: dict[str, str] | None = None,
    ) -> FakeAsyncContext:
        self.http_headers.append(headers)
        return FakeAsyncContext(FakeHTTPClient(headers), "http-client", self.events)

    def http_transport_factory(
        self,
        url: str,
        *,
        http_client: FakeHTTPClient | None = None,
        terminate_on_close: bool = True,
    ) -> FakeAsyncContext:
        assert terminate_on_close is True
        assert http_client is not None
        service_name = self.url_to_service[url]
        return FakeAsyncContext(
            (FakeReadStream(service_name), object(), lambda: f"session:{service_name}"),
            f"http-transport:{service_name}",
            self.events,
        )

    def stdio_transport_factory(self, server: object) -> FakeAsyncContext:
        command = getattr(server, "command")
        service_name = self.command_to_service[command]
        return FakeAsyncContext(
            (FakeReadStream(service_name), object()),
            f"stdio-transport:{service_name}",
            self.events,
        )

    def session_factory(self, read_stream: FakeReadStream, write_stream: object) -> FakeAsyncContext:
        del write_stream
        service_name = read_stream.service_name
        session = FakeSession(service_name, self._scripts[service_name], self.events)
        return FakeAsyncContext(session, f"session:{service_name}", self.events)


def test_connect_mcp_services_lists_tools_and_isolates_stdio_failures() -> None:
    """The runtime should keep one good service alive when another service fails."""

    scripts = {
        "weather": FakeServiceScript(
            list_tools_pages=[
                FakeListToolsResult(
                    tools=[
                        FakeTool(
                            name="lookup_weather",
                            description="Fetch the current weather.",
                            inputSchema={"type": "object", "properties": {"city": {"type": "string"}}},
                        )
                    ],
                    nextCursor="page-2",
                ),
                FakeListToolsResult(
                    tools=[
                        FakeTool(
                            name="lookup_forecast",
                            description="Fetch the weather forecast.",
                            inputSchema={"type": "object", "properties": {"city": {"type": "string"}}},
                        )
                    ]
                ),
            ]
        ),
        "filesystem": FakeServiceScript(
            initialize_error=RuntimeError("filesystem bootstrap failed"),
        ),
    }
    harness = FakeRuntimeHarness(scripts)

    weather = ServiceConfig(
        name="weather",
        transport=ServiceTransport.HTTP.value,
        url="https://weather.test/mcp",
        token="token-123",
        system_prompt="Use the weather tools.",
    )
    filesystem = ServiceConfig(
        name="filesystem",
        transport=ServiceTransport.STDIO.value,
        command="filesystem-cli",
        args=["/tmp"],
        system_prompt="Use the local filesystem tools.",
    )
    harness.url_to_service[weather.url or ""] = "weather"
    harness.command_to_service[filesystem.command or ""] = "filesystem"

    async def run_case() -> dict[str, object]:
        runtime = await connect_mcp_services(
            [weather, filesystem],
            session_factory=harness.session_factory,
            stdio_transport_factory=harness.stdio_transport_factory,
            http_transport_factory=harness.http_transport_factory,
            http_client_factory=harness.http_client_factory,
        )

        snapshot = {
            "results": runtime.results,
            "tools_by_service": runtime.tools_by_service,
            "system_prompts": runtime.system_prompts,
            "sessions": list(runtime.sessions),
            "http_headers": list(harness.http_headers),
            "weather_calls": list(scripts["weather"].list_tools_calls),
            "filesystem_calls": list(scripts["filesystem"].list_tools_calls),
        }

        await runtime.close()
        await runtime.close()
        snapshot["events"] = list(harness.events)
        return snapshot

    snapshot = asyncio.run(run_case())
    results = snapshot["results"]
    assert [result.service_name for result in results] == ["weather", "filesystem"]
    assert [result.transport for result in results] == ["http", "stdio"]
    assert results[0].ok is True
    assert [tool.name for tool in results[0].tools] == ["lookup_weather", "lookup_forecast"]
    assert results[0].system_prompt == "Use the weather tools."
    assert results[1].ok is False
    assert results[1].error == "filesystem bootstrap failed"

    tools_by_service = snapshot["tools_by_service"]
    assert list(tools_by_service) == ["weather"]
    assert [tool.name for tool in tools_by_service["weather"]] == [
        "lookup_weather",
        "lookup_forecast",
    ]
    assert snapshot["system_prompts"] == {"weather": "Use the weather tools."}
    assert snapshot["sessions"] == ["weather"]
    assert snapshot["http_headers"] == [{"Authorization": "Bearer token-123"}]
    assert snapshot["weather_calls"] == [None, "page-2"]
    assert snapshot["filesystem_calls"] == []

    events = snapshot["events"]
    assert "exit:session:filesystem" in events
    assert "exit:stdio-transport:filesystem" in events
    assert events.count("exit:http-client") == 1
    assert events.count("exit:http-transport:weather") == 1
    assert events.count("exit:session:weather") == 1