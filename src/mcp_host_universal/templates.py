"""Typed MCP service templates mirrored from the legacy Node host."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ServiceTransport(StrEnum):
    """Enumerate the transport kinds supported by the legacy config schema."""

    HTTP = "http"
    STDIO = "stdio"


@dataclass(frozen=True, slots=True)
class MCPServiceTemplate:
    """Describe one ready-made MCP service template from the legacy setup UI."""

    template_id: str
    label: str
    transport: ServiceTransport
    name: str
    system_prompt: str
    url: str | None = None
    token: str | None = None
    command: str | None = None
    args: tuple[str, ...] = ()

    def to_legacy_mapping(self) -> dict[str, object]:
        """Render the template using the field names expected by `config.json`."""

        payload: dict[str, object] = {
            "name": self.name,
            "transport": self.transport.value,
            "systemPrompt": self.system_prompt,
        }
        if self.url is not None:
            payload["url"] = self.url
        if self.token is not None:
            payload["token"] = self.token
        if self.command is not None:
            payload["command"] = self.command
        if self.args or self.command is not None:
            payload["args"] = list(self.args)
        return payload


MCP_SERVICE_TEMPLATES: tuple[MCPServiceTemplate, ...] = (
    MCPServiceTemplate(
        template_id="n8n",
        label="n8n (HTTP — padrão)",
        transport=ServiceTransport.HTTP,
        url="http://localhost:5678/mcp",
        token="",
        name="n8n",
        system_prompt="Você tem acesso ao n8n para criar, editar e executar workflows de automação.",
    ),
    MCPServiceTemplate(
        template_id="openrouter",
        label="OpenRouter MCP (HTTP)",
        transport=ServiceTransport.HTTP,
        url="https://openrouter.ai/mcp",
        token="",
        name="openrouter",
        system_prompt="Você tem acesso à API do OpenRouter para gerenciar modelos e créditos.",
    ),
    MCPServiceTemplate(
        template_id="filesystem",
        label="Filesystem (stdio — comando manual)",
        transport=ServiceTransport.STDIO,
        command="",
        args=(),
        name="filesystem",
        system_prompt="Você tem acesso ao sistema de arquivos local.",
    ),
    MCPServiceTemplate(
        template_id="custom-stdio",
        label="Personalizado — stdio",
        transport=ServiceTransport.STDIO,
        command="",
        args=(),
        name="",
        system_prompt="",
    ),
    MCPServiceTemplate(
        template_id="custom-http",
        label="Personalizado — HTTP",
        transport=ServiceTransport.HTTP,
        url="",
        token="",
        name="",
        system_prompt="",
    ),
)

_TEMPLATE_INDEX: dict[str, MCPServiceTemplate] = {
    template.template_id: template for template in MCP_SERVICE_TEMPLATES
}


def find_template(template_id: str) -> MCPServiceTemplate | None:
    """Return one legacy MCP template by id when the id is known."""

    return _TEMPLATE_INDEX.get(template_id)


__all__ = [
    "MCP_SERVICE_TEMPLATES",
    "MCPServiceTemplate",
    "ServiceTransport",
    "find_template",
]