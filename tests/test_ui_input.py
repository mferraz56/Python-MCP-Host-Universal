"""Focused tests for deterministic terminal input helpers."""

from __future__ import annotations

import pytest

from mcp_host_universal.ui.input import (
    FakeInputAdapter,
    InputCancelled,
    confirm_prompt,
    prompt_secret,
    prompt_text,
    select_option,
)


def test_select_option_wraps_with_keyboard_navigation() -> None:
    """Arrow-key navigation should wrap and return the chosen option."""

    adapter = FakeInputAdapter(["UP", "ENTER"])

    chosen = select_option(adapter, ["alpha", "beta", "gamma"], title="Escolha")

    assert chosen == "gamma"


def test_confirm_prompt_honors_default_and_explicit_no() -> None:
    """Confirm prompts should stay deterministic for empty and explicit answers."""

    keep_default = confirm_prompt(FakeInputAdapter(["ENTER"]), "Continuar?", default=True)
    reject = confirm_prompt(FakeInputAdapter(["n", "ENTER"]), "Continuar?", default=True)

    assert keep_default is True
    assert reject is False


def test_prompt_secret_masks_written_output() -> None:
    """Secret prompts should return the value without echoing the raw secret."""

    adapter = FakeInputAdapter(["secret-token", "ENTER"])

    value = prompt_secret(adapter, "API key: ")

    assert value == "secret-token"
    assert "secret-token" not in adapter.output
    assert "*" * len(value) in adapter.output


def test_prompt_text_raises_controlled_exception_on_ctrl_c() -> None:
    """Ctrl+C should stop the prompt with a controlled exception."""

    adapter = FakeInputAdapter(["CTRL_C"])

    with pytest.raises(InputCancelled):
        prompt_text(adapter, "Nome: ")