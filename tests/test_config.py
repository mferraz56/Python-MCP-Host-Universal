"""Focused tests for legacy `config.json` compatibility helpers."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mcp_host_universal.config import (
    ConfigDecodeError,
    HostConfig,
    load_config,
    resolve_config_path,
    save_config,
    user_config_path,
)


def test_user_config_path_is_windows_friendly() -> None:
    """Windows config discovery should respect APPDATA when it is available."""

    path = user_config_path(
        env={"APPDATA": r"C:\Users\muril\AppData\Roaming"},
        platform_name="win32",
    )

    assert path == Path(r"C:\Users\muril\AppData\Roaming\mcp-host-universal\config.json")


def test_resolve_config_path_prefers_existing_legacy_file(tmp_path: Path) -> None:
    """Existing legacy configs should win so the helper does not migrate files."""

    legacy_root = tmp_path / "project"
    legacy_root.mkdir()
    legacy_path = legacy_root / "config.json"
    legacy_path.write_text("{}\n", encoding="utf-8")

    resolved = resolve_config_path(
        root=legacy_root,
        home=tmp_path / "home",
        platform_name="win32",
    )

    assert resolved == legacy_path


def test_load_config_rejects_invalid_json(tmp_path: Path) -> None:
    """Invalid JSON should raise a controlled decode error."""

    config_path = tmp_path / "config.json"
    config_path.write_text('{"broken": ', encoding="utf-8")

    with pytest.raises(ConfigDecodeError, match="Invalid JSON"):
        load_config(config_path)


def test_legacy_config_round_trip_preserves_essential_fields(tmp_path: Path) -> None:
    """Loading and saving a legacy config should preserve its core schema."""

    config_path = tmp_path / "config.json"
    legacy_payload = {
        "_user": {
            "nome": "Murilo",
            "setupAt": "2026-05-28T12:00:00Z",
        },
        "openrouter": {
            "apiKey": "sk-test",
            "pago": False,
            "models": {
                "tools": ["openrouter/auto"],
                "final": ["meta-llama/llama-3.3-70b-instruct:free"],
            },
        },
        "services": [
            {
                "name": "n8n",
                "transport": "http",
                "url": "http://localhost:5678/mcp",
                "token": "token-123",
                "env": {"N8N_ENV": "local"},
                "systemPrompt": "Use o n8n.",
                "enabled": True,
                "timeout": 30,
            },
            {
                "name": "filesystem",
                "transport": "stdio",
                "command": "npx",
                "args": ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"],
                "env": {"HOME": "/tmp"},
                "systemPrompt": "Acesse arquivos locais.",
                "enabled": False,
                "cwd": "/workdir",
            },
        ],
        "theme": "legacy",
    }
    config_path.write_text(
        json.dumps(legacy_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    loaded = load_config(config_path)

    assert isinstance(loaded, HostConfig)
    assert loaded.user.nome == "Murilo"
    assert loaded.openrouter.paid is False
    assert loaded.openrouter.models.tools == ["openrouter/auto"]
    assert loaded.openrouter.models.final == ["meta-llama/llama-3.3-70b-instruct:free"]
    assert loaded.services[0].url == "http://localhost:5678/mcp"
    assert loaded.services[0].token == "token-123"
    assert loaded.services[0].env == {"N8N_ENV": "local"}
    assert loaded.services[0].extra["timeout"] == 30
    assert loaded.services[1].args == ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    assert loaded.services[1].env == {"HOME": "/tmp"}
    assert loaded.services[1].extra["cwd"] == "/workdir"
    assert loaded.extra["theme"] == "legacy"

    saved_path = save_config(loaded, config_path)
    saved_payload = json.loads(saved_path.read_text(encoding="utf-8"))

    assert saved_path == config_path
    assert saved_payload["_user"]["nome"] == "Murilo"
    assert saved_payload["_user"]["setupAt"] == "2026-05-28T12:00:00Z"
    assert saved_payload["openrouter"]["apiKey"] == "sk-test"
    assert saved_payload["openrouter"]["pago"] is False
    assert saved_payload["openrouter"]["models"]["tools"] == ["openrouter/auto"]
    assert saved_payload["openrouter"]["models"]["final"] == [
        "meta-llama/llama-3.3-70b-instruct:free"
    ]
    assert saved_payload["services"][0]["url"] == "http://localhost:5678/mcp"
    assert saved_payload["services"][0]["token"] == "token-123"
    assert saved_payload["services"][0]["env"] == {"N8N_ENV": "local"}
    assert saved_payload["services"][0]["timeout"] == 30
    assert saved_payload["services"][1]["command"] == "npx"
    assert saved_payload["services"][1]["args"] == [
        "-y",
        "@modelcontextprotocol/server-filesystem",
        "/tmp",
    ]
    assert saved_payload["services"][1]["env"] == {"HOME": "/tmp"}
    assert saved_payload["services"][1]["cwd"] == "/workdir"
    assert saved_payload["theme"] == "legacy"