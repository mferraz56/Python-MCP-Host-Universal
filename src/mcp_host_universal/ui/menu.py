"""Slash-menu primitives for the MCP Host interactive terminal UI."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from .input import BACKSPACE, CHAR, CTRL_C, ENTER, InputAdapter, InputCancelled, select_option


@dataclass(frozen=True, slots=True)
class SlashMenuItem:
    """Describe one top-level slash action exposed by the CLI menu."""

    command: str
    action: str
    label: str
    aliases: tuple[str, ...] = ()

    def matches(self, value: str) -> bool:
        """Return whether the provided text resolves to this action."""

        normalized = _normalize_command(value)
        return normalized == self.command or normalized in self.aliases


DEFAULT_SLASH_MENU_ITEMS: tuple[SlashMenuItem, ...] = (
    SlashMenuItem(
        command="/ferramentas",
        action="tools",
        label="Ver ferramentas por servico",
        aliases=("/tools",),
    ),
    SlashMenuItem(
        command="/servicos",
        action="services",
        label="Status dos servicos",
        aliases=("/services", "/status"),
    ),
    SlashMenuItem(
        command="/modelo",
        action="model",
        label="Trocar modelo ativo",
        aliases=("/model",),
    ),
    SlashMenuItem(
        command="/mcp",
        action="mcp_add",
        label="Adicionar servidor MCP",
        aliases=("/mcp-add",),
    ),
    SlashMenuItem(
        command="/mcp-list",
        action="mcp_list",
        label="Gerenciar servidores MCP",
    ),
    SlashMenuItem(
        command="/limpar",
        action="clear",
        label="Limpar historico",
        aliases=("/clear", "/reset"),
    ),
    SlashMenuItem(
        command="/ajuda",
        action="help",
        label="Ajuda",
        aliases=("/help",),
    ),
    SlashMenuItem(
        command="/sair",
        action="exit",
        label="Sair",
        aliases=("/exit", "/quit", "sair", "exit", "quit"),
    ),
)


def resolve_slash_command(
    text: str,
    *,
    items: Sequence[SlashMenuItem] = DEFAULT_SLASH_MENU_ITEMS,
) -> str | None:
    """Resolve one direct slash command or alias into a stable action id."""

    normalized = _normalize_command(text)
    if not normalized:
        return None

    for item in items:
        if item.matches(normalized):
            return item.action
    return None


def open_slash_menu(
    adapter: InputAdapter,
    *,
    items: Sequence[SlashMenuItem] = DEFAULT_SLASH_MENU_ITEMS,
) -> str:
    """Open the top-level slash menu and return the chosen action id."""

    chosen = select_option(
        adapter,
        items,
        title="Menu /",
        display=_display_item,
    )
    return chosen.action


def prompt_with_slash_menu(
    adapter: InputAdapter,
    *,
    prompt: str = "> ",
    items: Sequence[SlashMenuItem] = DEFAULT_SLASH_MENU_ITEMS,
) -> str:
    """Read text until Enter or open the slash menu when `/` starts the line."""

    buffer: list[str] = []
    adapter.write(prompt)

    while True:
        key = adapter.read_key()

        if key.kind == CTRL_C:
            adapter.write("\n")
            raise InputCancelled("Prompt cancelled by user.")

        if key.kind == ENTER:
            adapter.write("\n")
            value = "".join(buffer)
            return resolve_slash_command(value, items=items) or value

        if key.kind == BACKSPACE:
            if buffer:
                buffer.pop()
                adapter.write("\b \b")
            continue

        if key.kind != CHAR or not key.text:
            continue

        buffer.append(key.text)
        adapter.write(key.text)

        if len(buffer) == 1 and buffer[0] == "/":
            adapter.write("\n")
            return open_slash_menu(adapter, items=items)


def _display_item(item: SlashMenuItem) -> str:
    return f"{item.command:<12} {item.label}"


def _normalize_command(text: str) -> str:
    return text.strip().lower()


__all__ = [
    "DEFAULT_SLASH_MENU_ITEMS",
    "SlashMenuItem",
    "open_slash_menu",
    "prompt_with_slash_menu",
    "resolve_slash_command",
]