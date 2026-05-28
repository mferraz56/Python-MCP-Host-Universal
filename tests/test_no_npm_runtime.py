"""Focused checks for the Python-only CI and console entrypoint surface."""

from __future__ import annotations

import importlib
import re
import subprocess
import tomllib
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = PROJECT_ROOT / ".github" / "workflows"
LEGACY_RUNTIME_FILES = {"index.js", "package.json"}
DISALLOWED_WORKFLOW_PATTERN = re.compile(r"\b(?:npm|setup-node)\b", re.IGNORECASE)


def test_workflows_use_python_uv_without_node_surface() -> None:
    """The workflow surface should be Python-only and keep publish manual-disabled."""

    python_ci = (WORKFLOWS_DIR / "python-ci.yml").read_text(encoding="utf-8")
    disabled_publish = (WORKFLOWS_DIR / "npm-publish-github-packages.yml").read_text(encoding="utf-8")

    assert "actions/setup-python" in python_ci
    assert "astral-sh/setup-uv" in python_ci
    assert "uv sync --frozen --group dev" in python_ci
    assert "uv run pytest" in python_ci

    assert "workflow_dispatch:" in disabled_publish
    assert "release:" not in disabled_publish

    assert DISALLOWED_WORKFLOW_PATTERN.search(python_ci) is None
    assert DISALLOWED_WORKFLOW_PATTERN.search(disabled_publish) is None


def test_console_entrypoint_is_defined_in_pyproject_as_python_symbol() -> None:
    """The installed console script should resolve from the Python project metadata."""

    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    script_target = pyproject["project"]["scripts"]["mcp-host"]
    module_name, function_name = script_target.split(":")
    module = importlib.import_module(module_name)
    entrypoint = getattr(module, function_name)

    assert module_name == "mcp_host_universal.cli"
    assert function_name == "main"
    assert callable(entrypoint)
    assert entrypoint.__module__ == module_name
    assert ".js" not in script_target
    assert "node" not in script_target.lower()


def test_legacy_node_runtime_files_are_absent_and_untracked() -> None:
    """Legacy Node entrypoint artifacts should not remain in the repo surface."""

    for file_name in LEGACY_RUNTIME_FILES:
        assert not (PROJECT_ROOT / file_name).exists()

    tracked_files = subprocess.run(
        ["git", "ls-files"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()

    assert [path for path in tracked_files if Path(path).name in LEGACY_RUNTIME_FILES] == []