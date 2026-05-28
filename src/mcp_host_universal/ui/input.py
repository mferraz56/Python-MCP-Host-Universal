"""Deterministic input helpers for terminal and fake CLI interactions."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
import os
import sys
from typing import Protocol, TypeVar

CHAR = "char"
ENTER = "enter"
BACKSPACE = "backspace"
UP = "up"
DOWN = "down"
LEFT = "left"
RIGHT = "right"
CTRL_C = "ctrl_c"
EOF = "eof"

T = TypeVar("T")


class InputCancelled(Exception):
    """Raised when interactive input is cancelled with Ctrl+C."""


@dataclass(frozen=True, slots=True)
class KeyPress:
    """Represent one normalized key event from a terminal or fake adapter."""

    kind: str
    text: str = ""


class InputAdapter(Protocol):
    """Minimal protocol shared by terminal and fake input adapters."""

    def read_key(self) -> KeyPress:
        """Read the next normalized key event."""

    def write(self, text: str) -> None:
        """Write text to the active output surface."""


class FakeInputAdapter:
    """Feed deterministic key sequences into interactive helpers during tests."""

    def __init__(self, events: Iterable[str | KeyPress]) -> None:
        self._events = _expand_fake_events(events)
        self._output: list[str] = []

    def read_key(self) -> KeyPress:
        """Return the next fake key event or fail fast if the sequence is empty."""

        if not self._events:
            raise AssertionError("FakeInputAdapter has no more key events.")
        return self._events.pop(0)

    def write(self, text: str) -> None:
        """Capture written output for deterministic test assertions."""

        self._output.append(text)

    @property
    def output(self) -> str:
        """Expose the accumulated output transcript."""

        return "".join(self._output)


class TerminalInputAdapter:
    """Read raw key presses from the active terminal without invoking commands."""

    def __init__(self, *, input_stream: object | None = None, output_stream: object | None = None) -> None:
        self._input_stream = sys.stdin if input_stream is None else input_stream
        self._output_stream = sys.stdout if output_stream is None else output_stream

    def read_key(self) -> KeyPress:
        """Read one key press from the current terminal platform."""

        if os.name == "nt":
            return self._read_windows_key()
        return self._read_posix_key()

    def write(self, text: str) -> None:
        """Write terminal output immediately so prompts stay responsive."""

        self._output_stream.write(text)
        self._output_stream.flush()

    def _read_windows_key(self) -> KeyPress:
        import msvcrt

        value = msvcrt.getwch()
        if value in {"\x00", "\xe0"}:
            extended = msvcrt.getwch()
            return KeyPress(
                {
                    "H": UP,
                    "P": DOWN,
                    "K": LEFT,
                    "M": RIGHT,
                }.get(extended, CHAR),
                "" if extended in {"H", "P", "K", "M"} else extended,
            )
        return _normalize_terminal_key(value)

    def _read_posix_key(self) -> KeyPress:
        import termios
        import tty

        fileno = self._input_stream.fileno()
        previous = termios.tcgetattr(fileno)
        try:
            tty.setraw(fileno)
            first = self._input_stream.read(1)
            if first == "\x1b":
                second = self._input_stream.read(1)
                if second == "[":
                    third = self._input_stream.read(1)
                    mapping = {
                        "A": UP,
                        "B": DOWN,
                        "C": RIGHT,
                        "D": LEFT,
                    }
                    kind = mapping.get(third)
                    if kind is not None:
                        return KeyPress(kind)
                return KeyPress(CHAR, first)
            return _normalize_terminal_key(first)
        finally:
            termios.tcsetattr(fileno, termios.TCSADRAIN, previous)


def prompt_text(
    adapter: InputAdapter,
    prompt: str,
    *,
    secret: bool = False,
    mask: str = "*",
) -> str:
    """Collect one line of text from the adapter and return the entered value."""

    if len(mask) != 1:
        raise ValueError("mask must be a single character.")

    buffer: list[str] = []
    adapter.write(prompt)

    while True:
        key = adapter.read_key()

        if key.kind == CTRL_C:
            adapter.write("\n")
            raise InputCancelled("Input cancelled by user.")

        if key.kind == EOF:
            adapter.write("\n")
            return "".join(buffer)

        if key.kind == ENTER:
            adapter.write("\n")
            return "".join(buffer)

        if key.kind == BACKSPACE:
            if buffer:
                buffer.pop()
                adapter.write("\b \b")
            continue

        if key.kind != CHAR or not key.text:
            continue

        buffer.append(key.text)
        adapter.write(mask if secret else key.text)


def prompt_secret(adapter: InputAdapter, prompt: str, *, mask: str = "*") -> str:
    """Collect a masked secret value from the adapter."""

    return prompt_text(adapter, prompt, secret=True, mask=mask)


def confirm_prompt(adapter: InputAdapter, prompt: str, *, default: bool = True) -> bool:
    """Read a yes-or-no answer while keeping empty input deterministic."""

    hint = "(Y/n)" if default else "(y/N)"
    answer = prompt_text(adapter, f"{prompt} {hint} ").strip().lower()
    if not answer:
        return default
    if answer in {"y", "yes", "s", "sim", "1", "true"}:
        return True
    if answer in {"n", "no", "nao", "0", "false"}:
        return False
    return default


def select_option(
    adapter: InputAdapter,
    options: Sequence[T],
    *,
    title: str | None = None,
    display: Callable[[T], str] | None = None,
) -> T:
    """Navigate a list with arrow keys and return the chosen option."""

    if not options:
        raise ValueError("options must not be empty.")

    render = str if display is None else display
    selected_index = 0
    _render_options(adapter, options, selected_index, title=title, display=render)

    while True:
        key = adapter.read_key()

        if key.kind == CTRL_C:
            adapter.write("\n")
            raise InputCancelled("Selection cancelled by user.")

        if key.kind in {UP, LEFT}:
            selected_index = (selected_index - 1) % len(options)
            _render_options(adapter, options, selected_index, title=title, display=render)
            continue

        if key.kind in {DOWN, RIGHT}:
            selected_index = (selected_index + 1) % len(options)
            _render_options(adapter, options, selected_index, title=title, display=render)
            continue

        if key.kind == ENTER:
            adapter.write("\n")
            return options[selected_index]


def _render_options(
    adapter: InputAdapter,
    options: Sequence[T],
    selected_index: int,
    *,
    title: str | None,
    display: Callable[[T], str],
) -> None:
    lines: list[str] = []
    if title:
        lines.append(title)
    for index, option in enumerate(options):
        prefix = "> " if index == selected_index else "  "
        lines.append(f"{prefix}{display(option)}")
    adapter.write("\n".join(lines) + "\n")


def _expand_fake_events(events: Iterable[str | KeyPress]) -> list[KeyPress]:
    expanded: list[KeyPress] = []
    for event in events:
        if isinstance(event, KeyPress):
            expanded.append(event)
            continue

        normalized = event.strip().upper()
        special_kind = {
            "ENTER": ENTER,
            "BACKSPACE": BACKSPACE,
            "UP": UP,
            "DOWN": DOWN,
            "LEFT": LEFT,
            "RIGHT": RIGHT,
            "CTRL+C": CTRL_C,
            "CTRL_C": CTRL_C,
            "EOF": EOF,
        }.get(normalized)
        if special_kind is not None:
            expanded.append(KeyPress(special_kind))
            continue

        expanded.extend(KeyPress(CHAR, character) for character in event)
    return expanded


def _normalize_terminal_key(value: str) -> KeyPress:
    if value in {"", None}:
        return KeyPress(EOF)
    if value in {"\r", "\n"}:
        return KeyPress(ENTER)
    if value == "\x03":
        return KeyPress(CTRL_C)
    if value in {"\x08", "\x7f"}:
        return KeyPress(BACKSPACE)
    return KeyPress(CHAR, value)


__all__ = [
    "BACKSPACE",
    "CHAR",
    "CTRL_C",
    "DOWN",
    "EOF",
    "ENTER",
    "FakeInputAdapter",
    "InputAdapter",
    "InputCancelled",
    "KeyPress",
    "LEFT",
    "RIGHT",
    "TerminalInputAdapter",
    "UP",
    "confirm_prompt",
    "prompt_secret",
    "prompt_text",
    "select_option",
]