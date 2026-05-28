"""Module entrypoint for `python -m mcp_host_universal`."""

from __future__ import annotations

from .cli import main


def run() -> int:
    """Delegate module execution to the packaged CLI entrypoint."""
    return main()


if __name__ == "__main__":
    raise SystemExit(run())