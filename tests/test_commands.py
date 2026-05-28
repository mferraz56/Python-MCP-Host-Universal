"""Focused routing tests for typed slash-command handling."""

from __future__ import annotations

from pathlib import Path

import pytest

from mcp_host_universal.commands import handle_session_command
from mcp_host_universal.config import HostConfig, ServiceConfig
from mcp_host_universal.mcp_runtime import MCPServiceConnectionResult, MCPToolInfo
from mcp_host_universal.session import HostSessionState, SessionMessage
from mcp_host_universal.ui.input import FakeInputAdapter


def _build_state(
    *,
    services: list[ServiceConfig] | None = None,
    messages: list[SessionMessage] | None = None,
    connection_results: tuple[MCPServiceConnectionResult, ...] = (),
    tools_by_service: dict[str, tuple[MCPToolInfo, ...]] | None = None,
    config_path: Path | None = None,
) -> HostSessionState:
    return HostSessionState(
        config=HostConfig(services=list(services or [])),
        messages=list(messages or [SessionMessage(role="system", content="System prompt")]),
        connection_results=connection_results,
        tools_by_service=dict(tools_by_service or {}),
        config_path=config_path,
    )


def _recording_saver(save_calls: list[dict[str, object]], result_path: Path):
    def saver(config: HostConfig, path: str | Path | None = None) -> Path:
        save_calls.append({"path": path, "payload": config.to_mapping()})
        return result_path

    return saver


@pytest.mark.parametrize("command", ["/ajuda", "help"])
def test_handle_session_command_accepts_raw_slash_and_action_ids_for_help(command: str) -> None:
    """Help routing should accept both slash text and resolved menu action ids."""

    state = _build_state()

    result = handle_session_command(command, state)

    assert result.handled is True
    assert result.action == "help"
    assert ("/sair", "Encerrar.") in result.help_commands


def test_handle_session_command_returns_service_status_snapshot() -> None:
    """Service routing should expose the current connection snapshot unchanged."""

    connection_results = (
        MCPServiceConnectionResult(
            service_name="n8n",
            transport="http",
            ok=True,
            system_prompt="Use n8n.",
        ),
    )
    state = _build_state(connection_results=connection_results)

    result = handle_session_command("/servicos", state)

    assert result.handled is True
    assert result.action == "services"
    assert result.connection_results == connection_results


def test_handle_session_command_returns_tools_snapshot() -> None:
    """Tool routing should expose the cached tool catalog by service."""

    tools_by_service = {
        "n8n": (
            MCPToolInfo(
                name="n8n.list_workflows",
                description="List workflows.",
                input_schema={},
            ),
        ),
    }
    state = _build_state(tools_by_service=tools_by_service)

    result = handle_session_command("tools", state)

    assert result.handled is True
    assert result.action == "tools"
    assert result.tools_by_service["n8n"][0].name == "n8n.list_workflows"


def test_handle_session_command_clears_history_to_the_first_system_message() -> None:
    """Clear should keep the first system message and drop later chat messages."""

    state = _build_state(
        messages=[
            SessionMessage(role="system", content="Base system prompt"),
            SessionMessage(role="user", content="Oi"),
            SessionMessage(role="assistant", content="Ola"),
        ]
    )

    result = handle_session_command("/limpar", state)

    assert result.handled is True
    assert result.action == "clear"
    assert state.messages == [SessionMessage(role="system", content="Base system prompt")]


def test_handle_session_command_updates_model_and_saves_config(tmp_path: Path) -> None:
    """Model routing should call the existing selector, update both slots, and save."""

    save_calls: list[dict[str, object]] = []
    state = _build_state(config_path=tmp_path / "config.json")
    adapter = FakeInputAdapter(["DOWN", "ENTER"])

    result = handle_session_command(
        "model",
        state,
        adapter=adapter,
        save_config_fn=_recording_saver(save_calls, tmp_path / "saved-config.json"),
    )

    assert result.handled is True
    assert result.action == "model"
    assert result.saved is True
    assert result.model_id == "deepseek/deepseek-v4-flash:free"
    assert state.config.openrouter.models.tools == ["deepseek/deepseek-v4-flash:free"]
    assert state.config.openrouter.models.final == ["deepseek/deepseek-v4-flash:free"]
    assert save_calls[0]["payload"]["openrouter"]["models"]["tools"] == [
        "deepseek/deepseek-v4-flash:free"
    ]
    assert save_calls[0]["payload"]["openrouter"]["models"]["final"] == [
        "deepseek/deepseek-v4-flash:free"
    ]


def test_handle_session_command_appends_service_and_saves_config(tmp_path: Path) -> None:
    """MCP routing should call the existing configurator, append the service, and save."""

    save_calls: list[dict[str, object]] = []
    state = _build_state(config_path=tmp_path / "config.json")
    adapter = FakeInputAdapter(["DOWN", "ENTER", "ENTER", "ENTER", "ENTER", "ENTER"])

    result = handle_session_command(
        "/mcp",
        state,
        adapter=adapter,
        save_config_fn=_recording_saver(save_calls, tmp_path / "saved-config.json"),
    )

    assert result.handled is True
    assert result.action == "mcp_add"
    assert result.saved is True
    assert len(state.config.services) == 1
    assert state.config.services[0].name == "openrouter"
    assert state.config.services[0].url == "https://openrouter.ai/mcp"
    assert save_calls[0]["payload"]["services"][0]["name"] == "openrouter"
    assert save_calls[0]["payload"]["services"][0]["url"] == "https://openrouter.ai/mcp"


def test_handle_session_command_signals_exit() -> None:
    """Exit routing should signal the outer loop to stop without raising."""

    state = _build_state()

    result = handle_session_command("/sair", state)

    assert result.handled is True
    assert result.action == "exit"
    assert result.exit_requested is True


def test_handle_session_command_returns_controlled_error_for_unknown_commands() -> None:
    """Unknown commands should not crash the router or mutate the session state."""

    state = _build_state()

    result = handle_session_command("/desconhecido", state)

    assert result.handled is False
    assert result.action is None
    assert result.error == "Comando nao suportado: /desconhecido."


def test_handle_session_command_can_manage_mcp_services_from_injected_callback(
    tmp_path: Path,
) -> None:
    """The optional MCP list action should support deterministic service updates."""

    save_calls: list[dict[str, object]] = []
    state = _build_state(
        services=[
            ServiceConfig(name="n8n", transport="http", url="http://localhost:5678/mcp"),
            ServiceConfig(name="filesystem", transport="stdio", command="python", args=["-m", "demo"]),
        ],
        config_path=tmp_path / "config.json",
    )

    def manage_services(
        adapter: FakeInputAdapter,
        services: tuple[ServiceConfig, ...],
    ) -> tuple[ServiceConfig, ...]:
        assert isinstance(adapter, FakeInputAdapter)
        return services[1:]

    result = handle_session_command(
        "mcp_list",
        state,
        adapter=FakeInputAdapter([]),
        save_config_fn=_recording_saver(save_calls, tmp_path / "saved-config.json"),
        manage_services_fn=manage_services,
    )

    assert result.handled is True
    assert result.action == "mcp_list"
    assert result.saved is True
    assert [service.name for service in state.config.services] == ["filesystem"]
    assert [service["name"] for service in save_calls[0]["payload"]["services"]] == ["filesystem"]