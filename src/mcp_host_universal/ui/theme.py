"""Reusable terminal theme helpers for the Python CLI renderer."""

from __future__ import annotations

from dataclasses import dataclass
import os
import re

_ANSI_PATTERN = re.compile(r"\x1b\[[0-9;]*m")
_TONE_CODES: dict[str, str] = {
    "accent": "36",
    "muted": "90",
    "success": "32",
    "warning": "33",
    "error": "31",
    "info": "34",
    "header": "97",
}


@dataclass(frozen=True, slots=True)
class Theme:
    """Carry stable terminal styling settings for reusable render helpers."""

    color: bool = True
    width: int = 78
    test_mode: bool = False

    def apply(
        self,
        text: str,
        *,
        tone: str | None = None,
        bold: bool = False,
        dim: bool = False,
    ) -> str:
        """Apply ANSI styling when color output is enabled."""

        if not self.color or not text:
            return text

        codes: list[str] = []
        if bold:
            codes.append("1")
        if dim:
            codes.append("2")
        if tone is not None:
            code = _TONE_CODES.get(tone)
            if code is not None:
                codes.append(code)
        if not codes:
            return text
        return f"\x1b[{';'.join(codes)}m{text}\x1b[0m"


def build_theme(
    *,
    color: bool | None = None,
    test_mode: bool = False,
    width: int = 78,
) -> Theme:
    """Create a deterministic theme for interactive or test rendering."""

    if color is None:
        color = not (
            test_mode
            or bool(os.getenv("NO_COLOR"))
            or bool(os.getenv("PYTEST_CURRENT_TEST"))
        )

    if test_mode:
        color = False

    return Theme(color=bool(color), width=max(40, width), test_mode=test_mode)


def strip_ansi(text: str) -> str:
    """Remove ANSI control sequences from rendered output."""

    return _ANSI_PATTERN.sub("", text)


def visible_width(text: str) -> int:
    """Measure the display width of a rendered string."""

    return len(strip_ansi(text))


def pad_visible(text: str, width: int) -> str:
    """Pad a rendered string based on its visible width."""

    return f"{text}{' ' * max(0, width - visible_width(text))}"


__all__ = ["Theme", "build_theme", "pad_visible", "strip_ansi", "visible_width"]