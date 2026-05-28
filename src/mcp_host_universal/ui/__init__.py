"""Public terminal UI helpers for the Python MCP Host renderer slice."""

from .render import (
    DEFAULT_HELP_COMMANDS,
    render_badge,
    render_error,
    render_header,
    render_help,
    render_message,
    render_notice,
    render_table,
    render_tool_call,
    render_tool_result,
    render_tools_table,
)
from .theme import Theme, build_theme, pad_visible, strip_ansi, visible_width

__all__ = [
    "DEFAULT_HELP_COMMANDS",
    "Theme",
    "build_theme",
    "pad_visible",
    "render_badge",
    "render_error",
    "render_header",
    "render_help",
    "render_message",
    "render_notice",
    "render_table",
    "render_tool_call",
    "render_tool_result",
    "render_tools_table",
    "strip_ansi",
    "visible_width",
]