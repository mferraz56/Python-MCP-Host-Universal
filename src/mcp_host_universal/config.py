"""Typed config helpers for reading and writing legacy `config.json` files."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
import json
import os
from pathlib import Path
import sys
from typing import TypeAlias

from .models import default_openrouter_model

PathLike: TypeAlias = str | os.PathLike[str]
JSONScalar: TypeAlias = None | bool | int | float | str
JSONValue: TypeAlias = JSONScalar | list["JSONValue"] | dict[str, "JSONValue"]
JSONObject: TypeAlias = dict[str, JSONValue]

APP_NAME = "mcp-host-universal"
CONFIG_FILENAME = "config.json"


class ConfigError(Exception):
    """Base error for legacy config loading and validation failures."""


class ConfigDecodeError(ConfigError):
    """Raised when a config file exists but does not contain valid JSON."""


class ConfigValidationError(ConfigError):
    """Raised when parsed JSON does not match the expected object shape."""


def _copy_extra(data: Mapping[str, JSONValue], known_keys: set[str]) -> JSONObject:
    return {
        key: deepcopy(value)
        for key, value in data.items()
        if key not in known_keys
    }


def _string_or_default(value: object, default: str = "") -> str:
    return value if isinstance(value, str) else default


def _optional_string(value: object) -> str | None:
    return value if isinstance(value, str) else None


def _bool_or_default(value: object, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _string_mapping(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(item, str)
    }


@dataclass(slots=True)
class UserConfig:
    """Store the legacy `_user` block without forcing field migration."""

    nome: str = ""
    setup_at: str | None = None
    extra: JSONObject = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: object) -> UserConfig:
        """Build a user block from legacy JSON while preserving unknown keys."""

        if not isinstance(data, Mapping):
            return cls()
        payload = dict(data)
        setup_at = payload.get("setupAt")
        return cls(
            nome=_string_or_default(payload.get("nome")),
            setup_at=setup_at if isinstance(setup_at, str) else None,
            extra=_copy_extra(payload, {"nome", "setupAt"}),
        )

    def to_mapping(self) -> JSONObject:
        """Render the user block using legacy JSON field names."""

        payload = dict(self.extra)
        payload["nome"] = self.nome
        if self.setup_at is not None:
            payload["setupAt"] = self.setup_at
        return payload


@dataclass(slots=True)
class OpenRouterModelSelection:
    """Store the `openrouter.models` selections from the legacy config file."""

    tools: list[str] = field(default_factory=lambda: [default_openrouter_model(False).id])
    final: list[str] = field(default_factory=lambda: [default_openrouter_model(False).id])
    extra: JSONObject = field(default_factory=dict)

    @classmethod
    def default_for_account(cls, paid: bool) -> OpenRouterModelSelection:
        """Create the default tool/final selection for the account tier."""

        default_id = default_openrouter_model(paid).id
        return cls(tools=[default_id], final=[default_id])

    @classmethod
    def from_mapping(
        cls,
        data: object,
        *,
        paid: bool,
    ) -> OpenRouterModelSelection:
        """Build model selections from legacy JSON and keep unknown keys intact."""

        default_id = default_openrouter_model(paid).id
        if not isinstance(data, Mapping):
            return cls.default_for_account(paid)
        payload = dict(data)
        tools = _string_list(payload.get("tools")) or [default_id]
        final = _string_list(payload.get("final")) or [default_id]
        return cls(
            tools=tools,
            final=final,
            extra=_copy_extra(payload, {"tools", "final"}),
        )

    def to_mapping(self) -> JSONObject:
        """Render the model selection block using the legacy schema shape."""

        payload = dict(self.extra)
        payload["tools"] = list(self.tools)
        payload["final"] = list(self.final)
        return payload


@dataclass(slots=True)
class OpenRouterConfig:
    """Store the `openrouter` block from the legacy config schema."""

    api_key: str = ""
    paid: bool = False
    models: OpenRouterModelSelection = field(default_factory=OpenRouterModelSelection)
    extra: JSONObject = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: object) -> OpenRouterConfig:
        """Build the OpenRouter config block from legacy JSON."""

        if not isinstance(data, Mapping):
            return cls()
        payload = dict(data)
        paid = _bool_or_default(payload.get("pago"), False)
        return cls(
            api_key=_string_or_default(payload.get("apiKey")),
            paid=paid,
            models=OpenRouterModelSelection.from_mapping(payload.get("models"), paid=paid),
            extra=_copy_extra(payload, {"apiKey", "pago", "models"}),
        )

    def to_mapping(self) -> JSONObject:
        """Render the OpenRouter block using legacy field names."""

        payload = dict(self.extra)
        payload["apiKey"] = self.api_key
        payload["pago"] = self.paid
        payload["models"] = self.models.to_mapping()
        return payload


@dataclass(slots=True)
class ServiceConfig:
    """Store one MCP service entry while preserving unknown service keys."""

    name: str = ""
    transport: str = "http"
    url: str | None = None
    token: str | None = None
    command: str | None = None
    args: list[str] = field(default_factory=list)
    env: dict[str, str] = field(default_factory=dict)
    system_prompt: str = ""
    enabled: bool = True
    extra: JSONObject = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: object) -> ServiceConfig:
        """Build one service entry from legacy JSON while keeping extra fields."""

        if not isinstance(data, Mapping):
            return cls()
        payload = dict(data)
        return cls(
            name=_string_or_default(payload.get("name")),
            transport=_string_or_default(payload.get("transport"), "http"),
            url=_optional_string(payload.get("url")),
            token=_optional_string(payload.get("token")),
            command=_optional_string(payload.get("command")),
            args=_string_list(payload.get("args")),
            env=_string_mapping(payload.get("env")),
            system_prompt=_string_or_default(payload.get("systemPrompt")),
            enabled=_bool_or_default(payload.get("enabled"), True),
            extra=_copy_extra(
                payload,
                {
                    "name",
                    "transport",
                    "url",
                    "token",
                    "command",
                    "args",
                    "env",
                    "systemPrompt",
                    "enabled",
                },
            ),
        )

    def to_mapping(self) -> JSONObject:
        """Render one service entry using the legacy config field names."""

        payload = dict(self.extra)
        payload["name"] = self.name
        payload["transport"] = self.transport
        payload["systemPrompt"] = self.system_prompt
        payload["enabled"] = self.enabled
        if self.url is not None:
            payload["url"] = self.url
        if self.token is not None:
            payload["token"] = self.token
        if self.command is not None:
            payload["command"] = self.command
        if self.args or self.command is not None:
            payload["args"] = list(self.args)
        if self.env:
            payload["env"] = dict(self.env)
        return payload


@dataclass(slots=True)
class HostConfig:
    """Store the top-level legacy config shape as typed Python objects."""

    user: UserConfig = field(default_factory=UserConfig)
    openrouter: OpenRouterConfig = field(default_factory=OpenRouterConfig)
    services: list[ServiceConfig] = field(default_factory=list)
    extra: JSONObject = field(default_factory=dict)

    @classmethod
    def from_mapping(cls, data: object) -> HostConfig:
        """Build a typed config object from the legacy JSON document."""

        if not isinstance(data, Mapping):
            raise ConfigValidationError("Legacy config root must be a JSON object.")
        payload = dict(data)
        services_value = payload.get("services")
        services = []
        if isinstance(services_value, list):
            services = [
                ServiceConfig.from_mapping(entry)
                for entry in services_value
                if isinstance(entry, Mapping)
            ]
        return cls(
            user=UserConfig.from_mapping(payload.get("_user")),
            openrouter=OpenRouterConfig.from_mapping(payload.get("openrouter")),
            services=services,
            extra=_copy_extra(payload, {"_user", "openrouter", "services"}),
        )

    def to_mapping(self) -> JSONObject:
        """Render the config object back to the legacy `config.json` schema."""

        payload = dict(self.extra)
        payload["_user"] = self.user.to_mapping()
        payload["openrouter"] = self.openrouter.to_mapping()
        payload["services"] = [service.to_mapping() for service in self.services]
        return payload


def project_root(file_path: Path | None = None) -> Path:
    """Return the package project root for locating the legacy config file."""

    anchor = Path(__file__) if file_path is None else Path(file_path)
    return anchor.resolve().parents[2]


def legacy_config_path(
    *,
    root: Path | None = None,
    filename: str = CONFIG_FILENAME,
) -> Path:
    """Return the original install-local config path used by the Node host."""

    return (project_root() if root is None else Path(root)) / filename


def user_config_path(
    *,
    app_name: str = APP_NAME,
    filename: str = CONFIG_FILENAME,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
) -> Path:
    """Return an OS-appropriate user config path using stdlib only."""

    env_map = os.environ if env is None else env
    home_dir = Path.home() if home is None else Path(home)
    platform_value = sys.platform if platform_name is None else platform_name

    if platform_value.startswith("win"):
        base_dir = env_map.get("APPDATA")
        if base_dir:
            return Path(base_dir) / app_name / filename
        return home_dir / "AppData" / "Roaming" / app_name / filename

    if platform_value == "darwin":
        return home_dir / "Library" / "Application Support" / app_name / filename

    xdg_home = env_map.get("XDG_CONFIG_HOME")
    if xdg_home:
        return Path(xdg_home) / app_name / filename
    return home_dir / ".config" / app_name / filename


def resolve_config_path(
    path: PathLike | None = None,
    *,
    root: Path | None = None,
    app_name: str = APP_NAME,
    filename: str = CONFIG_FILENAME,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
    prefer_existing: bool = True,
) -> Path:
    """Choose an explicit, legacy, or OS-friendly config path without migrating data."""

    if path is not None:
        return Path(path)

    legacy_path = legacy_config_path(root=root, filename=filename)
    standard_path = user_config_path(
        app_name=app_name,
        filename=filename,
        env=env,
        home=home,
        platform_name=platform_name,
    )

    if prefer_existing:
        if legacy_path.exists():
            return legacy_path
        if standard_path.exists():
            return standard_path

    return standard_path


def load_config(
    path: PathLike | None = None,
    *,
    root: Path | None = None,
    app_name: str = APP_NAME,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
) -> HostConfig:
    """Load the legacy config file into typed Python objects."""

    config_path = resolve_config_path(
        path,
        root=root,
        app_name=app_name,
        env=env,
        home=home,
        platform_name=platform_name,
    )

    if not config_path.exists():
        return HostConfig()

    try:
        raw_data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ConfigDecodeError(
            f"Invalid JSON in {config_path} at line {error.lineno}, column {error.colno}."
        ) from error

    return HostConfig.from_mapping(raw_data)


def save_config(
    config: HostConfig,
    path: PathLike | None = None,
    *,
    root: Path | None = None,
    app_name: str = APP_NAME,
    env: Mapping[str, str] | None = None,
    home: Path | None = None,
    platform_name: str | None = None,
) -> Path:
    """Write a typed config object back to the legacy JSON schema."""

    config_path = resolve_config_path(
        path,
        root=root,
        app_name=app_name,
        env=env,
        home=home,
        platform_name=platform_name,
    )
    config_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(config.to_mapping(), ensure_ascii=False, indent=2)
    config_path.write_text(f"{payload}\n", encoding="utf-8")
    return config_path


__all__ = [
    "APP_NAME",
    "CONFIG_FILENAME",
    "ConfigDecodeError",
    "ConfigError",
    "ConfigValidationError",
    "HostConfig",
    "JSONObject",
    "JSONValue",
    "OpenRouterConfig",
    "OpenRouterModelSelection",
    "ServiceConfig",
    "UserConfig",
    "legacy_config_path",
    "load_config",
    "project_root",
    "resolve_config_path",
    "save_config",
    "user_config_path",
]