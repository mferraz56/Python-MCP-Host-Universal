"""Smoke tests for the Python package import and CLI entrypoints."""

from __future__ import annotations

import shutil
import subprocess
import sys

import mcp_host_universal


def test_package_import_exposes_version() -> None:
    """The package should import cleanly and expose a stable version string."""
    assert mcp_host_universal.__version__ == "1.0.8"


def test_module_entrypoint_help() -> None:
    """`python -m` should expose the CLI help output with a zero exit code."""
    result = subprocess.run(
        [sys.executable, "-m", "mcp_host_universal", "--help"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert "usage: mcp-host" in result.stdout
    assert "--version" in result.stdout


def test_console_entrypoint_version() -> None:
    """The generated console script should print the packaged version."""
    executable = shutil.which("mcp-host")

    assert executable is not None

    result = subprocess.run(
        [executable, "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0
    assert result.stdout.strip() == "mcp-host 1.0.8"


def test_unsupported_argument_exits_non_zero() -> None:
    """Unsupported arguments should fail fast with a concise error."""
    result = subprocess.run(
        [sys.executable, "-m", "mcp_host_universal", "--unsupported"],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 2
    assert result.stderr.strip() == "mcp-host: error: unrecognized arguments: --unsupported"