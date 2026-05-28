"""Focused secret-redaction checks for render and OpenRouter error helpers."""

from __future__ import annotations

from mcp_host_universal.openrouter import _safe_http_error, _sanitize_error_text
from mcp_host_universal.ui.render import render_tool_call, render_tool_result


def test_render_tool_call_redacts_api_key_bearer_and_token_like_values() -> None:
    """Tool call previews should not echo secret-bearing values."""

    rendered = render_tool_call(
        "search",
        "openrouter",
        {
            "apiKey": "sk-live-1234567890",
            "Authorization": "Bearer topsecret-token-value",
            "notes": "retry with sk-shadow-abcdef123456 if primary fails",
            "nested": {"token": "Bearer nested-secret-value"},
        },
        preview_limit=400,
    )

    assert "[redacted]" in rendered
    assert "sk-live-1234567890" not in rendered
    assert "topsecret-token-value" not in rendered
    assert "sk-shadow-abcdef123456" not in rendered
    assert "nested-secret-value" not in rendered


def test_render_tool_result_redacts_secret_assignments_in_text() -> None:
    """Tool result previews should sanitize inline secret strings."""

    rendered = render_tool_result(
        "Authorization: Bearer topsecret-token-value apiKey=sk-live-abcdef123456",
        is_error=True,
        preview_limit=400,
    )

    assert "[redacted]" in rendered
    assert "topsecret-token-value" not in rendered
    assert "sk-live-abcdef123456" not in rendered


def test_openrouter_sanitize_error_text_collapses_secret_heavy_messages() -> None:
    """Secret-heavy raw errors should collapse to one safe generic message."""

    sanitized = _sanitize_error_text(
        (
            'OpenRouter upstream rejected {"Authorization": "Bearer topsecret-token-value", '
            '"apiKey": "sk-live-abcdef123456"}'
        ),
        api_key="sk-configured-abcdef123456",
    )

    assert sanitized == "OpenRouter request failed."


def test_openrouter_safe_http_error_does_not_echo_standalone_token_like_values() -> None:
    """HTTP-safe errors should not leak raw key-like tokens from provider bodies."""

    secret = "sk-provider-abcdef123456"
    safe_error = _safe_http_error(
        502,
        f"Provider echoed {secret} while proxying the request.",
        api_key="sk-configured-abcdef123456",
    )

    assert safe_error == "OpenRouter request failed."
    assert secret not in safe_error
