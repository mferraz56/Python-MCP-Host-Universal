"""Route slash commands against the typed MCP Host session state."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal, Protocol, cast

from .config import HostConfig, PathLike, ServiceConfig, save_config
from .mcp_runtime import MCPServiceConnectionResult, MCPToolInfo
from .models import OpenRouterModel
from .onboarding import configure_service, select_openrouter_model
from .session import HostSessionState
from .ui.input import InputAdapter
from .ui.menu import resolve_slash_command

CommandAction = Literal[
    "tools",
    "services",
    "model",
    "mcp_add",
    "mcp_list",
    "clear",
    "help",
    "exit",
]

SUPPORTED_COMMAND_ACTIONS: tuple[CommandAction, ...] = (
    "tools",
    "services",
    "model",
    "mcp_add",
    "mcp_list",
    "clear",
    "help",
    "exit",
)
_SUPPORTED_ACTION_SET = frozenset(SUPPORTED_COMMAND_ACTIONS)


class ConfigSaver(Protocol):
    """Persist one typed host config and return the resolved config path."""

    def __call__(
        self,
        config: HostConfig,
        path: PathLike | None = None,
    ) -> PathLike: ...


class ModelSelector(Protocol):
    """Select one OpenRouter model using the active input adapter."""

    def __call__(self, adapter: InputAdapter, *, paid: bool) -> OpenRouterModel: ...


class ServiceConfigurator(Protocol):
    """Configure one MCP service using the active input adapter."""

    def __call__(self, adapter: InputAdapter) -> ServiceConfig: ...


class ServicesManager(Protocol):
    """Optionally manage the configured MCP service list from a custom UI."""

    def __call__(
        self,
        adapter: InputAdapter,
        services: Sequence[ServiceConfig],
    ) -> Sequence[ServiceConfig] | None: ...


@dataclass(frozen=True, slots=True)
class CommandResult:
    """Describe one routed slash-command outcome without rendering output."""

    action: CommandAction | None
    handled: bool
    exit_requested: bool = False
    message: str | None = None
    error: str | None = None
    saved: bool = False
    config_path: Path | None = None
    model_id: str | None = None
    service_name: str | None = None
    help_commands: tuple[tuple[str, str], ...] = ()
    connection_results: tuple[MCPServiceConnectionResult, ...] = ()
    tools_by_service: Mapping[str, tuple[MCPToolInfo, ...]] = field(default_factory=dict)
    services: tuple[ServiceConfig, ...] = ()


def resolve_command_action(command_or_action: str) -> CommandAction | None:
    """Resolve a raw slash command or menu action id into one known action."""

    normalized = command_or_action.strip().lower()
    if not normalized:
        return None

    if normalized in _SUPPORTED_ACTION_SET:
        return cast(CommandAction, normalized)

    resolved = resolve_slash_command(normalized)
    if resolved is None or resolved not in _SUPPORTED_ACTION_SET:
        return None
    return cast(CommandAction, resolved)


def handle_session_command(
    command_or_action: str,
    state: HostSessionState,
    *,
    adapter: InputAdapter | None = None,
    save_config_fn: ConfigSaver = save_config,
    select_model_fn: ModelSelector = select_openrouter_model,
    configure_service_fn: ServiceConfigurator = configure_service,
    manage_services_fn: ServicesManager | None = None,
) -> CommandResult:
    """Apply one slash command to the typed session state without network side effects."""

    action = resolve_command_action(command_or_action)
    if action is None:
        value = command_or_action.strip() or "<empty>"
        return CommandResult(
            action=None,
            handled=False,
            error=f"Comando nao suportado: {value}.",
        )

    if action == "services":
        return CommandResult(
            action=action,
            handled=True,
            message=f"{len(state.connection_results)} servico(s) no snapshot.",
            connection_results=state.connection_results,
        )

    if action == "tools":
        total_tools = sum(len(tools) for tools in state.tools_by_service.values())
        return CommandResult(
            action=action,
            handled=True,
            message=(
                f"{total_tools} ferramenta(s) em "
                f"{len(state.tools_by_service)} servico(s)."
            ),
            tools_by_service={
                service_name: tuple(tools)
                for service_name, tools in state.tools_by_service.items()
            },
        )

    if action == "help":
        return CommandResult(
            action=action,
            handled=True,
            message=f"{len(state.help_commands)} comando(s) disponivel(is).",
            help_commands=state.help_commands,
        )

    if action == "clear":
        state.clear_history()
        return CommandResult(
            action=action,
            handled=True,
            message="Historico limpo.",
        )

    if action == "exit":
        return CommandResult(
            action=action,
            handled=True,
            exit_requested=True,
            message="Sessao encerrada.",
        )

    if action == "model":
        if adapter is None:
            return _interactive_error(action, "Selecionar modelo exige um adapter interativo.")

        selected_model = select_model_fn(adapter, paid=state.config.openrouter.paid)
        state.set_active_model(selected_model.id)
        config_path = _save_session_config(state, save_config_fn)
        return CommandResult(
            action=action,
            handled=True,
            saved=True,
            config_path=config_path,
            model_id=selected_model.id,
            message=f"Modelo ativo atualizado para {selected_model.id}.",
        )

    if action == "mcp_add":
        if adapter is None:
            return _interactive_error(action, "Configurar MCP exige um adapter interativo.")

        service = configure_service_fn(adapter)
        state.append_service(service)
        config_path = _save_session_config(state, save_config_fn)
        return CommandResult(
            action=action,
            handled=True,
            saved=True,
            config_path=config_path,
            service_name=service.name,
            services=state.configured_services(),
            message=f"Servico MCP salvo: {service.name or '(sem nome)'}.",
        )

    services = state.configured_services()
    if manage_services_fn is None:
        return CommandResult(
            action=action,
            handled=True,
            services=services,
            message=f"{len(services)} servico(s) MCP configurado(s).",
        )

    if adapter is None:
        return _interactive_error(action, "Gerenciar MCP exige um adapter interativo.")

    updated_services = manage_services_fn(adapter, services)
    if updated_services is None:
        return CommandResult(
            action=action,
            handled=True,
            services=services,
            message="Nenhuma alteracao nos servicos MCP.",
        )

    normalized_services = tuple(updated_services)
    if normalized_services == services:
        return CommandResult(
            action=action,
            handled=True,
            services=services,
            message="Nenhuma alteracao nos servicos MCP.",
        )

    state.replace_services(normalized_services)
    config_path = _save_session_config(state, save_config_fn)
    return CommandResult(
        action=action,
        handled=True,
        saved=True,
        config_path=config_path,
        services=state.configured_services(),
        message="Servicos MCP atualizados.",
    )


def _interactive_error(action: CommandAction, message: str) -> CommandResult:
    return CommandResult(action=action, handled=True, error=message)


def _save_session_config(state: HostSessionState, save_config_fn: ConfigSaver) -> Path:
    """Persist the current config and keep the resolved path on the session state."""

    config_path = Path(save_config_fn(state.config, state.config_path))
    state.config_path = config_path
    return config_path


__all__ = [
    "CommandAction",
    "CommandResult",
    "ConfigSaver",
    "ModelSelector",
    "SUPPORTED_COMMAND_ACTIONS",
    "ServiceConfigurator",
    "ServicesManager",
    "handle_session_command",
    "resolve_command_action",
]