"""Drive first-run setup with the existing terminal adapters and typed config."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias

from .config import (
    APP_NAME,
    HostConfig,
    OpenRouterConfig,
    OpenRouterModelSelection,
    PathLike,
    ServiceConfig,
    UserConfig,
    save_config,
)
from .models import FREE_OPENROUTER_MODELS, PAID_OPENROUTER_MODELS, OpenRouterModel
from .templates import MCP_SERVICE_TEMPLATES, MCPServiceTemplate, ServiceTransport
from .ui.input import InputAdapter, confirm_prompt, prompt_secret, prompt_text, select_option
from .ui.render import render_header, render_notice
from .ui.theme import Theme

ServiceDescriptionGenerator: TypeAlias = Callable[[ServiceConfig, MCPServiceTemplate], str | None]


@dataclass(frozen=True, slots=True)
class OnboardingResult:
    """Return the saved config path, typed config, and transcript-safe summary."""

    config: HostConfig
    config_path: Path
    summary: str


def run_first_setup(
    adapter: InputAdapter,
    *,
    path: PathLike | None = None,
    root: Path | None = None,
    app_name: str = APP_NAME,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
    templates: Sequence[MCPServiceTemplate] = MCP_SERVICE_TEMPLATES,
    describe_service: ServiceDescriptionGenerator | None = None,
    theme: Theme | None = None,
) -> OnboardingResult:
    """Collect the first-run answers, save `config.json`, and print a safe summary."""

    adapter.write(
        render_header(
            "MCP Host Universal",
            "Configuracao inicial do host Python.",
            eyebrow="setup",
            theme=theme,
        )
        + "\n"
    )

    user_name = _prompt_required_text(adapter, "Nome", fallback="Usuario")
    api_key = prompt_secret(adapter, "OpenRouter API key: ").strip()
    paid_account = confirm_prompt(adapter, "Sua conta OpenRouter e paga?", default=False)
    selected_model = select_openrouter_model(adapter, paid=paid_account)
    service = configure_service(
        adapter,
        templates=templates,
        describe_service=describe_service,
    )

    config = build_first_setup_config(
        user_name=user_name,
        api_key=api_key,
        paid_account=paid_account,
        selected_model=selected_model,
        service=service,
    )
    config_path = save_config(
        config,
        path,
        root=root,
        app_name=app_name,
        env=env,
        home=home,
        platform_name=platform_name,
    )
    summary = render_onboarding_summary(config, selected_model, service, theme=theme)
    adapter.write(summary + "\n")
    return OnboardingResult(config=config, config_path=config_path, summary=summary)


def build_first_setup_config(
    *,
    user_name: str,
    api_key: str,
    paid_account: bool,
    selected_model: OpenRouterModel,
    service: ServiceConfig,
) -> HostConfig:
    """Build the typed config object for the first saved bootstrap setup."""

    return HostConfig(
        user=UserConfig(nome=user_name),
        openrouter=OpenRouterConfig(
            api_key=api_key,
            paid=paid_account,
            models=OpenRouterModelSelection(
                tools=[selected_model.id],
                final=[selected_model.id],
            ),
        ),
        services=[service],
    )


def select_openrouter_model(adapter: InputAdapter, *, paid: bool) -> OpenRouterModel:
    """Select one OpenRouter model from the paid or free catalog."""

    catalog = PAID_OPENROUTER_MODELS if paid else FREE_OPENROUTER_MODELS
    return select_option(
        adapter,
        catalog,
        title="Escolha o modelo OpenRouter",
        display=_display_model,
    )


def configure_service(
    adapter: InputAdapter,
    *,
    templates: Sequence[MCPServiceTemplate] = MCP_SERVICE_TEMPLATES,
    describe_service: ServiceDescriptionGenerator | None = None,
) -> ServiceConfig:
    """Select and configure one MCP service using the embedded template catalog."""

    chosen_template = select_option(
        adapter,
        list(templates),
        title="Escolha o primeiro servico MCP",
        display=_display_template,
    )
    return configure_service_from_template(
        adapter,
        chosen_template,
        describe_service=describe_service,
    )


def configure_service_from_template(
    adapter: InputAdapter,
    template: MCPServiceTemplate,
    *,
    describe_service: ServiceDescriptionGenerator | None = None,
) -> ServiceConfig:
    """Fill one service config from a template without contacting external systems."""

    service_name = _prompt_with_default(adapter, "Nome do servico", template.name or template.template_id)
    enabled = confirm_prompt(adapter, "Ativar servico agora?", default=True)

    if template.transport is ServiceTransport.HTTP:
        url = _prompt_with_default(adapter, "URL HTTP", template.url or "")
        token = prompt_secret(adapter, "Token HTTP (opcional): ").strip() or None
        service = ServiceConfig(
            name=service_name,
            transport=template.transport.value,
            url=url or None,
            token=token,
            system_prompt=template.system_prompt,
            enabled=enabled,
        )
    else:
        command = _prompt_with_default(adapter, "Comando stdio", template.command or "").strip() or None
        args_text = _prompt_with_default(adapter, "Argumentos stdio", " ".join(template.args)).strip()
        service = ServiceConfig(
            name=service_name,
            transport=template.transport.value,
            command=command,
            args=args_text.split() if args_text else [],
            system_prompt=template.system_prompt,
            enabled=enabled,
        )

    generated_description = None
    if describe_service is not None:
        generated_description = describe_service(service, template)
    if generated_description is not None and generated_description.strip():
        service.system_prompt = generated_description.strip()
    return service


def render_onboarding_summary(
    config: HostConfig,
    selected_model: OpenRouterModel,
    service: ServiceConfig,
    *,
    theme: Theme | None = None,
) -> str:
    """Render a short setup summary while masking all secrets in the transcript."""

    lines = [
        render_notice(f"Configuracao salva para {config.user.nome}.", level="success", theme=theme),
        render_notice(f"OpenRouter API key: {_mask_secret(config.openrouter.api_key)}", theme=theme),
        render_notice(f"Modelo ativo: {selected_model.id}", theme=theme),
        render_notice(f"Servico MCP: {service.name} ({service.transport})", theme=theme),
    ]

    if service.url:
        lines.append(render_notice(f"Endpoint: {service.url}", theme=theme))
    if service.command:
        lines.append(render_notice(f"Comando stdio: {service.command}", theme=theme))
    if service.token:
        lines.append(render_notice(f"Token do servico: {_mask_secret(service.token)}", theme=theme))

    return "\n".join(lines)


def _prompt_required_text(adapter: InputAdapter, label: str, *, fallback: str) -> str:
    """Read one text answer and fall back when the user leaves it blank."""

    return _prompt_with_default(adapter, label, fallback).strip() or fallback


def _prompt_with_default(adapter: InputAdapter, label: str, default: str) -> str:
    """Read one value while allowing blank input to keep the provided default."""

    suffix = f" [{default}]" if default else ""
    value = prompt_text(adapter, f"{label}{suffix}: ").strip()
    return value or default


def _display_model(model: OpenRouterModel) -> str:
    return f"{model.label} ({model.context_window})"


def _display_template(template: MCPServiceTemplate) -> str:
    return template.label


def _mask_secret(value: str) -> str:
    if not value:
        return "(nao configurada)"
    return "********"


__all__ = [
    "OnboardingResult",
    "ServiceDescriptionGenerator",
    "build_first_setup_config",
    "configure_service",
    "configure_service_from_template",
    "render_onboarding_summary",
    "run_first_setup",
    "select_openrouter_model",
]