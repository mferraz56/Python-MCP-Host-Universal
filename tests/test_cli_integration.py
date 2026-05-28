"""Focused smoke tests for the integrated Python CLI."""

from __future__ import annotations

from pathlib import Path

import mcp_host_universal.cli as cli
from mcp_host_universal.config import HostConfig, OpenRouterConfig, OpenRouterModelSelection, ServiceConfig, save_config
from mcp_host_universal.mcp_runtime import MCPRuntime, MCPServiceConnectionResult
from mcp_host_universal.ui.input import FakeInputAdapter


class UnexpectedOpenRouterClient:
    """Fail fast when the CLI should stay offline."""

    def __init__(self, api_key: str) -> None:
        raise AssertionError(f"OpenRouterClient should not be created: {api_key}")


def test_one_shot_without_tools_reports_offline_chat_and_skips_model_calls(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Prompt mode should stay offline when no MCP tools are available."""

    config_path = tmp_path / "config.json"
    _write_config(config_path)
    monkeypatch.setattr(cli, "OpenRouterClient", UnexpectedOpenRouterClient)

    exit_code = cli.main(["--config", str(config_path), "--prompt", "Oi"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "chat sem ferramentas mcp" in captured.out.lower()


def test_missing_api_key_triggers_onboarding_before_one_shot_mode(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Missing config or API key should route through onboarding before prompt mode."""

    config_path = tmp_path / "config.json"
    adapter = FakeInputAdapter(
        [
            "Murilo",
            "ENTER",
            "sk-test-onboarding",
            "ENTER",
            "ENTER",
            "ENTER",
            "ENTER",
            "ENTER",
            "ENTER",
            "ENTER",
            "ENTER",
        ]
    )

    async def fake_connect(services: list[ServiceConfig]) -> MCPRuntime:
        assert len(services) == 1
        return MCPRuntime(results=(), tools_by_service={}, system_prompts={})

    monkeypatch.setattr(cli, "TerminalInputAdapter", lambda: adapter)
    monkeypatch.setattr(cli, "connect_mcp_services", fake_connect)
    monkeypatch.setattr(cli, "OpenRouterClient", UnexpectedOpenRouterClient)

    exit_code = cli.main(["--config", str(config_path), "--prompt", "Oi"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert config_path.exists()
    assert "configuracao salva para murilo" in adapter.output.lower()
    assert "chat sem ferramentas mcp" in captured.out.lower()


def test_one_shot_survives_mcp_connection_failures_and_stays_offline(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Connection failures should render status and keep the CLI usable."""

    config_path = tmp_path / "config.json"
    _write_config(
        config_path,
        services=[
            ServiceConfig(
                name="demo",
                transport="http",
                url="http://localhost:9999/mcp",
            )
        ],
    )

    async def fake_connect(services: list[ServiceConfig]) -> MCPRuntime:
        assert [service.name for service in services] == ["demo"]
        return MCPRuntime(
            results=(
                MCPServiceConnectionResult(
                    service_name="demo",
                    transport="http",
                    ok=False,
                    error="backend offline",
                ),
            ),
            tools_by_service={},
            system_prompts={},
        )

    monkeypatch.setattr(cli, "connect_mcp_services", fake_connect)
    monkeypatch.setattr(cli, "OpenRouterClient", UnexpectedOpenRouterClient)

    exit_code = cli.main(["--config", str(config_path), "--prompt", "Oi"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "backend offline" in captured.out.lower()
    assert "chat sem ferramentas mcp" in captured.out.lower()


def test_one_shot_can_render_help_command_without_openrouter(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    """Prompt mode should route slash commands through the session command handler."""

    config_path = tmp_path / "config.json"
    _write_config(config_path)
    monkeypatch.setattr(cli, "OpenRouterClient", UnexpectedOpenRouterClient)

    exit_code = cli.main(["--config", str(config_path), "--prompt", "/ajuda"])
    captured = capsys.readouterr()

    assert exit_code == 0
    assert "comandos" in captured.out.lower()
    assert "/sair" in captured.out


def _write_config(
    path: Path,
    *,
    api_key: str = "sk-test-cli",
    services: list[ServiceConfig] | None = None,
) -> None:
    save_config(
        HostConfig(
            openrouter=OpenRouterConfig(
                api_key=api_key,
                models=OpenRouterModelSelection(
                    tools=["demo-model"],
                    final=["demo-model"],
                ),
            ),
            services=list(services or []),
        ),
        path=path,
    )