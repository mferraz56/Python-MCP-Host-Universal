"""Typed OpenRouter model catalog for the legacy MCP Host config schema."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class OpenRouterModel:
    """Describe one selectable OpenRouter model from the legacy host catalog."""

    id: str
    label: str
    context_window: str
    paid: bool


PAID_OPENROUTER_MODELS: tuple[OpenRouterModel, ...] = (
    OpenRouterModel(
        id="anthropic/claude-sonnet-4-5",
        label="Claude Sonnet 4.5",
        context_window="200k",
        paid=True,
    ),
    OpenRouterModel(
        id="anthropic/claude-opus-4",
        label="Claude Opus 4",
        context_window="200k",
        paid=True,
    ),
    OpenRouterModel(
        id="openai/gpt-4o",
        label="GPT-4o",
        context_window="128k",
        paid=True,
    ),
    OpenRouterModel(
        id="openai/gpt-4-turbo",
        label="GPT-4 Turbo",
        context_window="128k",
        paid=True,
    ),
    OpenRouterModel(
        id="google/gemini-2.5-pro",
        label="Gemini 2.5 Pro",
        context_window="1M",
        paid=True,
    ),
    OpenRouterModel(
        id="google/gemini-2.5-flash",
        label="Gemini 2.5 Flash",
        context_window="1M",
        paid=True,
    ),
    OpenRouterModel(
        id="meta-llama/llama-3.3-70b-instruct",
        label="Llama 3.3 70B",
        context_window="128k",
        paid=True,
    ),
    OpenRouterModel(
        id="mistralai/mistral-large",
        label="Mistral Large",
        context_window="128k",
        paid=True,
    ),
    OpenRouterModel(
        id="deepseek/deepseek-chat",
        label="DeepSeek Chat V3",
        context_window="64k",
        paid=True,
    ),
    OpenRouterModel(
        id="qwen/qwen-2.5-72b-instruct",
        label="Qwen 2.5 72B",
        context_window="128k",
        paid=True,
    ),
)

FREE_OPENROUTER_MODELS: tuple[OpenRouterModel, ...] = (
    OpenRouterModel(
        id="openrouter/auto",
        label="⚡ Auto Router (recomendado)",
        context_window="—",
        paid=False,
    ),
    OpenRouterModel(
        id="deepseek/deepseek-v4-flash:free",
        label="DeepSeek V4 Flash (free)",
        context_window="64k",
        paid=False,
    ),
    OpenRouterModel(
        id="nvidia/nemotron-3-super-120b-a12b:free",
        label="Nemotron 3 Super 120B (free)",
        context_window="128k",
        paid=False,
    ),
    OpenRouterModel(
        id="meta-llama/llama-3.3-70b-instruct:free",
        label="Llama 3.3 70B (free)",
        context_window="128k",
        paid=False,
    ),
    OpenRouterModel(
        id="nousresearch/hermes-3-llama-3.1-405b:free",
        label="Hermes 3 Llama 405B (free)",
        context_window="128k",
        paid=False,
    ),
    OpenRouterModel(
        id="minimax/minimax-m2.5:free",
        label="MiniMax M2.5 (free)",
        context_window="1M",
        paid=False,
    ),
    OpenRouterModel(
        id="google/gemma-4-31b-it:free",
        label="Gemma 4 31B (free)",
        context_window="128k",
        paid=False,
    ),
    OpenRouterModel(
        id="openai/gpt-oss-120b:free",
        label="GPT OSS 120B (free)",
        context_window="128k",
        paid=False,
    ),
    OpenRouterModel(
        id="qwen/qwen3-coder-480b-a35b-instruct:free",
        label="Qwen3 Coder 480B (free)",
        context_window="128k",
        paid=False,
    ),
)

ALL_OPENROUTER_MODELS: tuple[OpenRouterModel, ...] = (
    PAID_OPENROUTER_MODELS + FREE_OPENROUTER_MODELS
)

_MODEL_INDEX: dict[str, OpenRouterModel] = {
    model.id: model for model in ALL_OPENROUTER_MODELS
}


def default_openrouter_model(paid: bool) -> OpenRouterModel:
    """Return the default model entry for paid or free OpenRouter accounts."""

    return PAID_OPENROUTER_MODELS[0] if paid else FREE_OPENROUTER_MODELS[0]


def find_openrouter_model(model_id: str) -> OpenRouterModel | None:
    """Return the known catalog entry for a legacy OpenRouter model id."""

    return _MODEL_INDEX.get(model_id)


__all__ = [
    "ALL_OPENROUTER_MODELS",
    "FREE_OPENROUTER_MODELS",
    "PAID_OPENROUTER_MODELS",
    "OpenRouterModel",
    "default_openrouter_model",
    "find_openrouter_model",
]