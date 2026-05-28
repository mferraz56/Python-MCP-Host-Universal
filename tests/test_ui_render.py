"""Focused tests for the reusable terminal UI rendering helpers."""

from __future__ import annotations

from mcp_host_universal.ui import (
    build_theme,
    render_badge,
    render_error,
    render_header,
    render_help,
    render_message,
    render_notice,
    render_tool_call,
    render_tool_result,
    render_tools_table,
)


def test_render_help_and_tools_table_in_no_color_mode() -> None:
    """The smoke slice should render help and a fake tools table without ANSI."""

    theme = build_theme(color=False, test_mode=True, width=72)

    help_output = render_help(theme=theme)
    tools_output = render_tools_table(
        "n8n",
        [
            {
                "name": "fake_tool_name",
                "description": "Fake tool used for slice smoke coverage.",
            }
        ],
        theme=theme,
    )
    combined_output = f"{help_output}\n\n{tools_output}"

    assert "/ajuda" in combined_output
    assert "/servicos" in combined_output
    assert "fake_tool_name" in combined_output
    assert "\x1b[" not in combined_output


def test_renderers_redact_secret_values_from_plain_data() -> None:
    """Tool previews and messages should not leak obvious secrets."""

    theme = build_theme(color=False, test_mode=True)

    tool_call = render_tool_call(
        "deploy_workflow",
        "n8n",
        {
            "token": "abc123-secret",
            "Authorization": "Bearer very-secret-token",
            "path": "/tmp/workflow.json",
        },
        theme=theme,
    )
    tool_result = render_tool_result(
        {
            "status": "ok",
            "apiKey": "sk-live-1234567890",
        },
        theme=theme,
    )
    message = render_message(
        "assistant",
        "Use token=abc123-secret and sk-live-1234567890 only on the server side.",
        theme=theme,
    )

    combined_output = f"{tool_call}\n{tool_result}\n{message}"

    assert "[redacted]" in combined_output
    assert "abc123-secret" not in combined_output
    assert "sk-live-1234567890" not in combined_output
    assert "very-secret-token" not in combined_output


def test_render_fragments_cover_header_badges_messages_and_errors() -> None:
    """The slice should expose the reusable fragments needed by later cards."""

    theme = build_theme(color=False, test_mode=True, width=60)

    header = render_header(
        "MCP Host Universal",
        "Python terminal renderer",
        eyebrow="beta",
        theme=theme,
    )
    badge = render_badge("tool", tone="warning", theme=theme)
    notice = render_notice("Connected to fake service.", level="success", theme=theme)
    message = render_message(
        "assistant",
        "First line.\n- second line",
        timestamp="12:34",
        theme=theme,
    )
    error = render_error("Failed to load one service.", theme=theme)
    result = render_tool_result("x" * 400, theme=theme)

    assert "MCP Host Universal" in header
    assert "[TOOL]" == badge
    assert "Connected to fake service." in notice
    assert "[ASSISTANT] 12:34" in message
    assert "Failed to load one service." in error
    assert "..." in result