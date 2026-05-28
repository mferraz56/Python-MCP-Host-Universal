"""Executable CLI for MCP Host Universal."""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import NoReturn

from . import __version__
from .chat import run_chat_turn
from .commands import CommandResult, handle_session_command, resolve_command_action
from .config import ConfigError, HostConfig, PathLike, load_config, resolve_config_path
from .mcp_runtime import MCPRuntime, MCPServiceConnectionResult, MCPToolInfo, connect_mcp_services
from .onboarding import run_first_setup
from .openrouter import OpenRouterClient, OpenRouterError
from .session import HostSessionState
from .ui.input import InputAdapter, InputCancelled, TerminalInputAdapter
from .ui.menu import prompt_with_slash_menu
from .ui.render import (
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


class MCPHostArgumentParser(argparse.ArgumentParser):
    """Emit concise non-zero CLI errors for unsupported arguments."""

    def error(self, message: str) -> NoReturn:
        """Exit with a short argparse error message on invalid usage."""
        self.exit(2, f"{self.prog}: error: {message}\n")


def build_parser() -> argparse.ArgumentParser:
    """Build the executable `mcp-host` parser."""

    parser = MCPHostArgumentParser(
        prog="mcp-host",
        description="Interactive CLI for MCP Host Universal.",
    )
    parser.add_argument(
        "--config",
        help="Path to the config.json file.",
    )
    parser.add_argument(
        "--prompt",
        help="Run one non-interactive prompt and exit.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """Run the packaged CLI entrypoint."""

    parser = build_parser()
    args = list(sys.argv[1:] if argv is None else argv)
    namespace = parser.parse_args(args)

    try:
        return asyncio.run(_run_cli(namespace))
    except (InputCancelled, KeyboardInterrupt):
        _write_line(render_notice("Sessao encerrada.", level="warning"))
        return 130


async def _run_cli(args: argparse.Namespace) -> int:
    config_path = resolve_config_path(args.config)
    try:
        config = load_config(args.config)
    except ConfigError as exc:
        _write_line(render_error(str(exc)))
        return 1

    adapter: InputAdapter | None = None
    if _needs_onboarding(config, config_path):
        adapter = TerminalInputAdapter()
        onboarding = run_first_setup(adapter, path=config_path)
        config = onboarding.config
        config_path = onboarding.config_path

    runtime = await _connect_runtime(config.services)
    try:
        state = HostSessionState(
            config=config,
            connection_results=runtime.results,
            tools_by_service=dict(runtime.tools_by_service),
            config_path=config_path,
        )
        _render_session_bootstrap(config_path, runtime, one_shot=args.prompt is not None)

        if args.prompt is not None:
            return await _run_one_shot_mode(args.prompt, state, runtime)

        session_adapter = adapter or TerminalInputAdapter()
        return await _run_interactive_loop(session_adapter, state, runtime)
    finally:
        await runtime.close()


async def _run_one_shot_mode(
    prompt: str,
    state: HostSessionState,
    runtime: MCPRuntime,
) -> int:
    if _looks_like_command(prompt):
        result = handle_session_command(prompt, state)
        _render_command_result(result)
        return 0 if result.error is None else 1

    if not _runtime_has_tools(runtime):
        _write_line(
            render_notice(
                "Chat sem ferramentas MCP; prompt nao enviado ao modelo.",
                level="warning",
            )
        )
        return 0

    return await _run_chat_prompt(state, runtime, prompt)


async def _run_interactive_loop(
    adapter: InputAdapter,
    state: HostSessionState,
    runtime: MCPRuntime,
) -> int:
    active_runtime = runtime
    _write_line(render_help(state.help_commands))
    _write_line(render_notice("Digite / para abrir o menu de comandos.", level="info"))

    try:
        while True:
            try:
                value = prompt_with_slash_menu(adapter, prompt="mcp-host> ")
            except InputCancelled:
                _write_line(render_notice("Sessao encerrada.", level="warning"))
                return 0

            if not value.strip():
                continue

            if _looks_like_command(value):
                result = handle_session_command(value, state, adapter=adapter)
                _render_command_result(result)

                if result.action in {"mcp_add", "mcp_list"} and result.saved:
                    new_runtime = await _connect_runtime(state.config.services)
                    await active_runtime.close()
                    active_runtime = new_runtime
                    _sync_runtime_snapshot(state, active_runtime)
                    _render_runtime_snapshot(active_runtime.results)

                if result.exit_requested:
                    return 0
                continue

            if not _runtime_has_tools(active_runtime):
                _write_line(
                    render_notice(
                        "Chat sem ferramentas MCP; ajuste os servicos antes de conversar.",
                        level="warning",
                    )
                )
                continue

            await _run_chat_prompt(state, active_runtime, value)
    finally:
        await active_runtime.close()


async def _run_chat_prompt(
    state: HostSessionState,
    runtime: MCPRuntime,
    prompt: str,
) -> int:
    try:
        result = await run_chat_turn(
            state,
            runtime,
            prompt,
            client=OpenRouterClient(state.config.openrouter.api_key),
        )
    except OpenRouterError as exc:
        _write_line(render_error(str(exc)))
        return 1
    except Exception as exc:  # pragma: no cover - defensive CLI boundary.
        _write_line(render_error(str(exc)))
        return 1

    _render_chat_events(result.events, runtime)
    return 0


async def _connect_runtime(services: Sequence[object]) -> MCPRuntime:
    try:
        return await connect_mcp_services(services)
    except Exception as exc:  # pragma: no cover - defensive CLI boundary.
        _write_line(
            render_notice(
                "Falha ao conectar servicos MCP; a sessao continua utilizavel.",
                level="warning",
            )
        )
        _write_line(render_error(str(exc)))
        return MCPRuntime(results=(), tools_by_service={}, system_prompts={})


def _needs_onboarding(config: HostConfig, config_path: PathLike) -> bool:
    path = Path(config_path)
    return not path.exists() or not config.openrouter.api_key.strip()


def _looks_like_command(value: str) -> bool:
    return value.lstrip().startswith("/") or resolve_command_action(value) is not None


def _runtime_has_tools(runtime: MCPRuntime) -> bool:
    return any(runtime.tools_by_service.values())


def _sync_runtime_snapshot(state: HostSessionState, runtime: MCPRuntime) -> None:
    state.connection_results = runtime.results
    state.tools_by_service = dict(runtime.tools_by_service)


def _render_session_bootstrap(
    config_path: Path,
    runtime: MCPRuntime,
    *,
    one_shot: bool,
) -> None:
    _write_line(
        render_header(
            "MCP Host Universal",
            "CLI Python para onboarding, MCP, comandos e chat.",
            eyebrow="cli",
        )
    )
    _write_line(render_notice(f"Config: {config_path}", level="success"))
    _render_runtime_snapshot(runtime.results)
    if one_shot:
        return
    _write_line(render_notice("Sessao pronta.", level="success"))


def _render_runtime_snapshot(results: Sequence[MCPServiceConnectionResult]) -> None:
    if not results:
        _write_line(render_notice("Nenhum servico MCP configurado.", level="warning"))
        return

    rows = [
        (
            result.service_name,
            result.transport,
            "ok" if result.ok else "erro",
            f"{len(result.tools)} ferramenta(s)" if result.ok else (result.error or "Falha desconhecida."),
        )
        for result in results
    ]
    _write_line(
        render_table(
            "Servicos MCP",
            ("Servico", "Transporte", "Status", "Detalhe"),
            rows,
        )
    )


def _render_command_result(result: CommandResult) -> None:
    if result.error:
        _write_line(render_error(result.error))

    if result.message:
        level = "success" if result.saved else "info"
        _write_line(render_notice(result.message, level=level))

    if result.help_commands:
        _write_line(render_help(result.help_commands))

    if result.connection_results:
        _render_runtime_snapshot(result.connection_results)

    if result.tools_by_service:
        for service_name, tools in result.tools_by_service.items():
            _write_line(
                render_tools_table(
                    service_name,
                    [
                        {
                            "name": tool.name,
                            "description": tool.description or "",
                        }
                        for tool in tools
                    ],
                )
            )

    if result.services:
        rows = [
            (
                service.name or "(sem nome)",
                service.transport,
                service.url or service.command or "-",
                "ativo" if service.enabled else "desativado",
            )
            for service in result.services
        ]
        _write_line(
            render_table(
                "Servicos configurados",
                ("Servico", "Transporte", "Destino", "Status"),
                rows,
            )
        )

    if result.saved and result.config_path is not None:
        _write_line(render_notice(f"Config salva em {result.config_path}", level="success"))


def _render_chat_events(events: Sequence[object], runtime: MCPRuntime) -> None:
    tool_services = _tool_service_map(runtime.tools_by_service)

    for event in events:
        message = event.message
        if message.role == "assistant" and message.tool_calls:
            if message.content.strip():
                _write_line(render_message(message.role, message.content))
            for tool_call in message.tool_calls:
                _write_line(
                    render_tool_call(
                        tool_call.name,
                        tool_services.get(tool_call.name, "mcp"),
                        tool_call.arguments,
                    )
                )
            continue

        if message.role == "tool":
            _write_line(render_tool_result(message.content, is_error=event.is_error))
            continue

        _write_line(render_message(message.role, message.content))


def _tool_service_map(
    tools_by_service: dict[str, tuple[MCPToolInfo, ...]],
) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for service_name, tools in tools_by_service.items():
        for tool in tools:
            mapping[tool.name] = service_name
    return mapping


def _write_line(text: str) -> None:
    sys.stdout.write(f"{text}\n")