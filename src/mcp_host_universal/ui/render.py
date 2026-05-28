"""Pure terminal rendering helpers for the Python MCP Host UI slice."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
import re
import textwrap

from .theme import Theme, build_theme

DEFAULT_HELP_COMMANDS: tuple[tuple[str, str], ...] = (
    ("/", "Abre menu interativo com comandos, servicos e ferramentas."),
    ("/servicos", "Status dos servicos conectados."),
    ("/ferramentas", "Lista ferramentas por servico."),
    ("/modelo", "Trocar modelo ativo."),
    ("/mcp", "Configurar ou adicionar servidor MCP."),
    ("/limpar", "Limpa historico da conversa."),
    ("/ajuda", "Esta ajuda."),
    ("/sair", "Encerrar."),
)

_SECRET_MARKER = "[redacted]"
_SECRET_JSON_DOUBLE_PATTERN = re.compile(
    r'(?i)("(?:api[_-]?key|token|password|secret|authorization|access[_-]?token|refresh[_-]?token)"\s*:\s*")([^"]*)(")'
)
_SECRET_JSON_SINGLE_PATTERN = re.compile(
    r"(?i)('(?:api[_-]?key|token|password|secret|authorization|access[_-]?token|refresh[_-]?token)'\s*:\s*')([^']*)(')"
)
_SECRET_ASSIGNMENT_PATTERN = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret|authorization|access[_-]?token|refresh[_-]?token)\b(\s*[:=]\s*)([^\s,}]+)"
)
_ENV_SECRET_PATTERN = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API_KEY|TOKEN|PASSWORD|SECRET))\b(\s*=\s*)(\S+)"
)
_BEARER_PATTERN = re.compile(r"(?i)(bearer\s+)[A-Za-z0-9._=-]{6,}")
_KEYLIKE_PATTERN = re.compile(r"(?i)\bsk-[A-Za-z0-9_-]{6,}\b")


def render_header(
    title: str,
    subtitle: str | None = None,
    *,
    eyebrow: str | None = None,
    theme: Theme | None = None,
) -> str:
    """Render a banner-style header for one terminal screen."""

    resolved_theme = _resolve_theme(theme)
    width = resolved_theme.width
    lines: list[str] = [resolved_theme.apply("=" * width, tone="muted", dim=True)]

    if eyebrow:
        lines.append(render_badge(eyebrow, tone="accent", theme=resolved_theme))

    title_text = _sanitize_text(title).strip()
    lines.append(resolved_theme.apply(title_text.center(width), tone="header", bold=True))

    if subtitle:
        for line in _wrap_block(_sanitize_text(subtitle), width):
            lines.append(line.center(width) if len(line) < width else line)

    lines.append(resolved_theme.apply("=" * width, tone="muted", dim=True))
    return "\n".join(lines)


def render_help(
    commands: Sequence[object] = DEFAULT_HELP_COMMANDS,
    *,
    theme: Theme | None = None,
) -> str:
    """Render the static help menu used by later CLI screens."""

    resolved_theme = _resolve_theme(theme)
    normalized = [_normalize_help_command(entry) for entry in commands]
    command_width = max((len(command) for command, _ in normalized), default=10)
    description_width = max(20, resolved_theme.width - command_width - 7)

    lines: list[str] = []
    for command, description in normalized:
        wrapped = _wrap_block(description, description_width)
        first_line = wrapped[0] if wrapped else ""
        lines.append(f"{command.ljust(command_width)} {first_line}".rstrip())
        for continuation in wrapped[1:]:
            lines.append(f"{' ' * command_width} {continuation}".rstrip())

    return _render_panel(lines, title="Comandos", theme=resolved_theme, tone="accent")


def render_table(
    title: str,
    columns: Sequence[str],
    rows: Sequence[Sequence[object]],
    *,
    theme: Theme | None = None,
    empty_message: str = "Sem dados.",
) -> str:
    """Render a boxed table from plain row data."""

    resolved_theme = _resolve_theme(theme)
    column_list = [str(column) for column in columns]
    normalized_rows = [
        [_stringify_value(cell) for cell in row]
        for row in rows
    ]

    if not normalized_rows:
        normalized_rows = [[empty_message] + ["" for _ in column_list[1:]]]

    widths = _compute_column_widths(column_list, normalized_rows, resolved_theme.width)
    border = _table_border(widths)
    title_line = resolved_theme.apply(_sanitize_text(title), tone="accent", bold=True)

    lines: list[str] = [title_line, border, _table_row(column_list, widths), border]
    for row in normalized_rows:
        wrapped_row_lines = _wrap_table_row(row, widths)
        for row_line in wrapped_row_lines:
            lines.append(_table_row(row_line, widths))
    lines.append(border)
    return "\n".join(lines)


def render_tools_table(
    service_name: str,
    tools: Sequence[Mapping[str, object]],
    *,
    theme: Theme | None = None,
) -> str:
    """Render a tool catalog table for one service using plain mappings."""

    rows: list[tuple[str, str, str]] = []
    for index, tool in enumerate(tools, start=1):
        name = _mapping_value(tool, "name", "tool", "id")
        description = _mapping_value(tool, "description", "summary", "details")
        rows.append((str(index), name, description))

    safe_service_name = _sanitize_text(service_name).upper() or "UNKNOWN"
    return render_table(
        f"Ferramentas - {safe_service_name}",
        ("#", "Ferramenta", "Descricao"),
        rows,
        theme=theme,
        empty_message="Nenhuma ferramenta registrada.",
    )


def render_badge(
    label: str,
    *,
    tone: str = "muted",
    theme: Theme | None = None,
) -> str:
    """Render a small reusable badge for message prefixes and status lines."""

    resolved_theme = _resolve_theme(theme)
    text = f"[{_sanitize_text(label).upper()}]"
    return resolved_theme.apply(text, tone=tone, bold=True)


def render_message(
    role: str,
    text: str,
    *,
    timestamp: str | None = None,
    theme: Theme | None = None,
) -> str:
    """Render one chat-like message block without interactive behavior."""

    resolved_theme = _resolve_theme(theme)
    tone = {
        "user": "accent",
        "assistant": "info",
        "system": "muted",
        "tool": "warning",
    }.get(role.lower(), "muted")
    header = render_badge(role, tone=tone, theme=resolved_theme)
    if timestamp:
        header = f"{header} {timestamp}"

    prefix = resolved_theme.apply("|", tone="muted", dim=True)
    body_lines = _sanitize_text(text).splitlines() or [""]
    rendered_lines = [header]
    for line in body_lines:
        rendered_lines.append(prefix if not line else f"{prefix} {line}")
    return "\n".join(rendered_lines)


def render_notice(
    message: str,
    *,
    level: str = "info",
    theme: Theme | None = None,
) -> str:
    """Render one single-line status message with a severity badge."""

    tone = {
        "info": "info",
        "success": "success",
        "warning": "warning",
        "error": "error",
    }.get(level.lower(), "muted")
    return f"{render_badge(level, tone=tone, theme=theme)} {_sanitize_text(message)}"


def render_error(message: str, *, theme: Theme | None = None) -> str:
    """Render one boxed error block."""

    return _render_panel(
        [_sanitize_text(message)],
        title="ERROR",
        theme=_resolve_theme(theme),
        tone="error",
    )


def render_tool_call(
    tool_name: str,
    service_name: str,
    arguments: object,
    *,
    theme: Theme | None = None,
    preview_limit: int = 100,
) -> str:
    """Render a single tool invocation preview while redacting secrets."""

    preview = _truncate(_single_line(_stringify_value(arguments)), preview_limit)
    return (
        f"{render_badge('tool', tone='warning', theme=theme)} "
        f"[{_sanitize_text(service_name)}] {_sanitize_text(tool_name)} -> {preview}"
    )


def render_tool_result(
    result: object,
    *,
    is_error: bool = False,
    theme: Theme | None = None,
    preview_limit: int = 220,
) -> str:
    """Render one tool result preview from plain text or structured data."""

    preview = _truncate(_single_line(_stringify_value(result)), preview_limit)
    label = "ERROR" if is_error else "RESULT"
    tone = "error" if is_error else "muted"
    return f"{render_badge(label, tone=tone, theme=theme)} {preview}"


def _resolve_theme(theme: Theme | None) -> Theme:
    if theme is None:
        return build_theme()
    return theme


def _normalize_help_command(entry: object) -> tuple[str, str]:
    if isinstance(entry, Mapping):
        command = _stringify_value(entry.get("command") or entry.get("name") or "")
        description = _stringify_value(entry.get("description") or entry.get("label") or "")
        return command, description

    if isinstance(entry, Sequence) and not isinstance(entry, str):
        parts = list(entry)
        command = _stringify_value(parts[0] if parts else "")
        description = _stringify_value(parts[1] if len(parts) > 1 else "")
        return command, description

    return _stringify_value(entry), ""


def _mapping_value(mapping: Mapping[str, object], *keys: str) -> str:
    for key in keys:
        if key in mapping:
            return _stringify_value(mapping[key], key=key)
    return ""


def _render_panel(
    lines: Sequence[str],
    *,
    title: str | None,
    theme: Theme,
    tone: str,
) -> str:
    inner_width = max(20, theme.width - 4)
    wrapped_lines: list[str] = []
    for line in lines:
        wrapped_lines.extend(_wrap_block(_sanitize_text(line), inner_width))
    if not wrapped_lines:
        wrapped_lines.append("")

    title_text = _truncate(_sanitize_text(title or ""), inner_width)
    if title_text:
        title_block = f" {title_text} "
        fill = max(0, inner_width + 2 - len(title_block))
        top = f"+{title_block}{'-' * fill}+"
    else:
        top = f"+{'-' * (inner_width + 2)}+"
    bottom = f"+{'-' * (inner_width + 2)}+"

    rendered_lines = [theme.apply(top, tone=tone, dim=tone == "muted")]
    for line in wrapped_lines:
        rendered_lines.append(f"| {line.ljust(inner_width)} |")
    rendered_lines.append(theme.apply(bottom, tone=tone, dim=tone == "muted"))
    return "\n".join(rendered_lines)


def _compute_column_widths(
    columns: Sequence[str],
    rows: Sequence[Sequence[str]],
    total_width: int,
) -> list[int]:
    minima = [max(3, len(column)) for column in columns]
    targets = minima[:]
    for index, column in enumerate(columns):
        column_width = len(column)
        for row in rows:
            if index < len(row):
                cell_lines = row[index].splitlines() or [row[index]]
                column_width = max(column_width, *(len(line) for line in cell_lines))
        capped_width = min(column_width, 40 if index == len(columns) - 1 else 24)
        targets[index] = max(minima[index], capped_width)

    available = max(sum(minima), total_width - (3 * len(columns) + 1))
    while sum(targets) > available:
        widest_index = max(range(len(targets)), key=lambda idx: targets[idx] - minima[idx])
        if targets[widest_index] <= minima[widest_index]:
            break
        targets[widest_index] -= 1
    return targets


def _table_border(widths: Sequence[int]) -> str:
    return "+" + "+".join("-" * (width + 2) for width in widths) + "+"


def _table_row(values: Sequence[str], widths: Sequence[int]) -> str:
    padded = []
    for index, width in enumerate(widths):
        value = values[index] if index < len(values) else ""
        padded.append(f" {value.ljust(width)} ")
    return "|" + "|".join(padded) + "|"


def _wrap_table_row(row: Sequence[str], widths: Sequence[int]) -> list[list[str]]:
    wrapped_cells = [_wrap_block(cell, width) for cell, width in zip(row, widths, strict=False)]
    while len(wrapped_cells) < len(widths):
        wrapped_cells.append([""])
    height = max(len(cell_lines) for cell_lines in wrapped_cells)

    row_lines: list[list[str]] = []
    for line_index in range(height):
        row_lines.append(
            [
                cell_lines[line_index] if line_index < len(cell_lines) else ""
                for cell_lines in wrapped_cells
            ]
        )
    return row_lines


def _wrap_block(text: str, width: int) -> list[str]:
    source_lines = text.splitlines() or [""]
    wrapped_lines: list[str] = []
    for source_line in source_lines:
        parts = textwrap.wrap(
            source_line,
            width=width,
            break_long_words=True,
            break_on_hyphens=False,
        )
        wrapped_lines.extend(parts or [""])
    return wrapped_lines


def _stringify_value(value: object, *, key: str | None = None) -> str:
    normalized = _normalize_value(value, key=key)
    if isinstance(normalized, str):
        return normalized
    try:
        return json.dumps(normalized, ensure_ascii=True, sort_keys=True)
    except TypeError:
        return _sanitize_text(str(normalized), key=key)


def _normalize_value(value: object, *, key: str | None = None) -> object:
    if key is not None and _is_secret_key(key):
        return _SECRET_MARKER

    if isinstance(value, Mapping):
        return {
            str(item_key): _normalize_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }

    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_normalize_value(item) for item in value]

    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"

    if value is None or isinstance(value, (bool, int, float)):
        return value

    return _sanitize_text(str(value), key=key)


def _sanitize_text(text: str, *, key: str | None = None) -> str:
    if key is not None and _is_secret_key(key):
        return _SECRET_MARKER

    sanitized = text.replace("\r\n", "\n").replace("\r", "\n")
    sanitized = _SECRET_JSON_DOUBLE_PATTERN.sub(rf"\1{_SECRET_MARKER}\3", sanitized)
    sanitized = _SECRET_JSON_SINGLE_PATTERN.sub(rf"\1{_SECRET_MARKER}\3", sanitized)
    sanitized = _BEARER_PATTERN.sub(rf"\1{_SECRET_MARKER}", sanitized)
    sanitized = _KEYLIKE_PATTERN.sub(_SECRET_MARKER, sanitized)
    sanitized = _ENV_SECRET_PATTERN.sub(_replace_env_secret, sanitized)
    sanitized = _SECRET_ASSIGNMENT_PATTERN.sub(_replace_secret_assignment, sanitized)
    return sanitized


def _replace_env_secret(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}{_SECRET_MARKER}"


def _replace_secret_assignment(match: re.Match[str]) -> str:
    return f"{match.group(1)}{match.group(2)}{_SECRET_MARKER}"


def _is_secret_key(key: str) -> bool:
    normalized = re.sub(r"[^a-z0-9]+", "", key.lower())
    return (
        normalized in {
            "apikey",
            "accesstoken",
            "authorization",
            "authtoken",
            "cookie",
            "openrouterapikey",
            "password",
            "refreshtoken",
            "secret",
            "session",
            "token",
        }
        or normalized.endswith("apikey")
        or normalized.endswith("token")
        or normalized.endswith("password")
        or normalized.endswith("secret")
    )


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    if limit <= 3:
        return text[:limit]
    return f"{text[: limit - 3]}..."


def _single_line(text: str) -> str:
    return " ".join(text.split())


__all__ = [
    "DEFAULT_HELP_COMMANDS",
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
]