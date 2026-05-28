"""Regression tests for the typed legacy model and template catalogs."""

from __future__ import annotations

from mcp_host_universal.models import (
    FREE_OPENROUTER_MODELS,
    PAID_OPENROUTER_MODELS,
    default_openrouter_model,
    find_openrouter_model,
)
from mcp_host_universal.templates import (
    ServiceTransport,
    find_template,
)


def test_openrouter_catalog_separates_paid_and_free_models() -> None:
    """The typed catalog should preserve the legacy paid/free model split."""

    assert len(PAID_OPENROUTER_MODELS) == 10
    assert len(FREE_OPENROUTER_MODELS) == 9
    assert default_openrouter_model(False).id == "openrouter/auto"
    assert default_openrouter_model(True).id == "anthropic/claude-sonnet-4-5"
    assert find_openrouter_model("openai/gpt-4o") == PAID_OPENROUTER_MODELS[2]
    assert find_openrouter_model("openrouter/auto") == FREE_OPENROUTER_MODELS[0]
    assert find_openrouter_model("does-not-exist") is None


def test_templates_cover_http_defaults_and_manual_filesystem_stdio() -> None:
    """The typed template catalog should keep HTTP defaults and manual filesystem stdio."""

    openrouter = find_template("openrouter")
    filesystem = find_template("filesystem")
    custom_http = find_template("custom-http")

    assert openrouter is not None
    assert openrouter.transport is ServiceTransport.HTTP
    assert openrouter.url == "https://openrouter.ai/mcp"

    assert filesystem is not None
    assert filesystem.transport is ServiceTransport.STDIO
    assert filesystem.command == ""
    assert filesystem.args == ()
    assert filesystem.label == "Filesystem (stdio — comando manual)"
    assert filesystem.to_legacy_mapping()["command"] == ""
    assert filesystem.to_legacy_mapping()["args"] == []

    assert custom_http is not None
    assert custom_http.to_legacy_mapping() == {
        "name": "",
        "transport": "http",
        "systemPrompt": "",
        "url": "",
        "token": "",
    }