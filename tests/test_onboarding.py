"""Focused smoke tests for the first-run onboarding flow."""

from __future__ import annotations

import json
from pathlib import Path

from mcp_host_universal.onboarding import run_first_setup
from mcp_host_universal.templates import MCP_SERVICE_TEMPLATES, find_template
from mcp_host_universal.ui.input import FakeInputAdapter
from mcp_host_universal.ui.theme import build_theme


def test_run_first_setup_creates_config_and_masks_secrets(tmp_path: Path) -> None:
    """The fake onboarding flow should save config without echoing secrets."""

    config_path = tmp_path / "config.json"
    adapter = FakeInputAdapter(
        [
            "Murilo",
            "ENTER",
            "sk-test-onboarding",
            "ENTER",
            "n",
            "ENTER",
            "DOWN",
            "ENTER",
            "ENTER",
            "ENTER",
            "ENTER",
            "ENTER",
            "n8n-token",
            "ENTER",
        ]
    )

    result = run_first_setup(
        adapter,
        path=config_path,
        theme=build_theme(color=False, test_mode=True),
    )

    saved_payload = json.loads(config_path.read_text(encoding="utf-8"))

    assert result.config_path == config_path
    assert result.config.user.nome == "Murilo"
    assert result.config.openrouter.models.tools == ["deepseek/deepseek-v4-flash:free"]
    assert result.config.openrouter.models.final == ["deepseek/deepseek-v4-flash:free"]
    assert result.config.services[0].name == "n8n"
    assert result.config.services[0].transport == "http"
    assert result.config.services[0].url == "http://localhost:5678/mcp"
    assert result.config.services[0].token == "n8n-token"
    assert saved_payload["_user"]["nome"] == "Murilo"
    assert saved_payload["openrouter"]["apiKey"] == "sk-test-onboarding"
    assert saved_payload["openrouter"]["models"]["tools"] == ["deepseek/deepseek-v4-flash:free"]
    assert saved_payload["services"][0]["name"] == "n8n"
    assert saved_payload["services"][0]["transport"] == "http"
    assert saved_payload["services"][0]["url"] == "http://localhost:5678/mcp"
    assert saved_payload["services"][0]["token"] == "n8n-token"
    assert "sk-test-onboarding" not in adapter.output
    assert "n8n-token" not in adapter.output
    assert "OpenRouter API key: ********" in adapter.output
    assert "Token do servico: ********" in adapter.output


def test_run_first_setup_accepts_optional_service_description_generator(tmp_path: Path) -> None:
    """The service description hook should stay optional and fully mockable."""

    adapter = FakeInputAdapter(
        [
            "Ana",
            "ENTER",
            "sk-optional-description",
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

    result = run_first_setup(
        adapter,
        path=tmp_path / "config.json",
        describe_service=lambda service, template: (
            f"Servico {service.name} via {template.transport.value} sem rede."
        ),
        theme=build_theme(color=False, test_mode=True),
    )

    assert result.config.services[0].system_prompt == "Servico n8n via http sem rede."


def test_embedded_templates_do_not_require_npm_or_npx() -> None:
    """Embedded templates should not depend on npm or npx during onboarding."""

    commands = {template.command for template in MCP_SERVICE_TEMPLATES}
    filesystem = find_template("filesystem")

    assert "npm" not in commands
    assert "npx" not in commands
    assert filesystem is not None
    assert filesystem.command == ""
    assert filesystem.args == ()