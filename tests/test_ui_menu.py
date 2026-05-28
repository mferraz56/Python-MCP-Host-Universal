"""Focused tests for the deterministic slash menu helpers."""

from __future__ import annotations

import pytest

from mcp_host_universal.ui.input import FakeInputAdapter, InputCancelled
from mcp_host_universal.ui.menu import open_slash_menu, prompt_with_slash_menu, resolve_slash_command


@pytest.mark.parametrize(
    ("command", "expected_action"),
    [
        ("/help", "help"),
        ("/services", "services"),
        ("/mcp", "mcp_add"),
        ("/quit", "exit"),
    ],
)
def test_resolve_slash_command_supports_current_js_aliases(
    command: str,
    expected_action: str,
) -> None:
    """Direct slash aliases should map to the same top-level actions as the JS CLI."""

    assert resolve_slash_command(command) == expected_action


def test_open_slash_menu_returns_help_action() -> None:
    """Keyboard navigation should resolve the help item from the top-level menu."""

    adapter = FakeInputAdapter(["DOWN", "DOWN", "DOWN", "DOWN", "DOWN", "DOWN", "ENTER"])

    action = open_slash_menu(adapter)

    assert action == "help"


def test_prompt_with_slash_menu_returns_help_from_trigger_sequence() -> None:
    """Typing `/` should open the slash menu and return the selected action."""

    adapter = FakeInputAdapter(["/", "DOWN", "DOWN", "DOWN", "DOWN", "DOWN", "DOWN", "ENTER"])

    action = prompt_with_slash_menu(adapter, prompt="> ")

    assert action == "help"


def test_prompt_with_slash_menu_raises_controlled_exception_on_ctrl_c() -> None:
    """Ctrl+C should abort the slash prompt without exiting the process."""

    adapter = FakeInputAdapter(["CTRL_C"])

    with pytest.raises(InputCancelled):
        prompt_with_slash_menu(adapter)