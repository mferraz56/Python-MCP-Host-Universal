"""Async OpenRouter helpers for safe model fallback and tool-aware calls."""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final
from urllib import error, request

OPENROUTER_URL: Final[str] = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MAX_TOKENS: Final[int] = 8192
DEFAULT_TEMPERATURE: Final[float] = 0.1
_TOOL_TEXT_MARKERS: Final[tuple[str, ...]] = (
    "<tool_call>",
    "<function=",
    "```tool_call",
    '"function":',
    "tool_use",
)
_JAVASCRIPT_BLOCK_RE: Final[re.Pattern[str]] = re.compile(
    r"```(?:javascript|js)?\s*([\s\S]+?)```"
)
_AUTHORIZATION_RE: Final[re.Pattern[str]] = re.compile(
    r"Authorization\s*:\s*Bearer\s+[^\s,;\"']+",
    re.IGNORECASE,
)
_QUOTED_AUTHORIZATION_RE: Final[re.Pattern[str]] = re.compile(
    r"[\"']Authorization[\"']\s*:\s*[\"']Bearer\s+[^\"']+[\"']",
    re.IGNORECASE,
)
_BEARER_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"Bearer\s+[A-Za-z0-9._:-]+",
    re.IGNORECASE,
)
_KEYLIKE_TOKEN_RE: Final[re.Pattern[str]] = re.compile(
    r"\bsk-[A-Za-z0-9._=-]{6,}\b",
    re.IGNORECASE,
)
_SECRET_WORD_RE: Final[re.Pattern[str]] = re.compile(
    r"authorization|bearer|api[ _-]?key|token",
    re.IGNORECASE,
)

SleepHook = Callable[[float], Awaitable[None]]
BackoffHook = Callable[[int], float]


class OpenRouterError(RuntimeError):
    """Report one short safe OpenRouter failure."""


@dataclass(frozen=True, slots=True)
class OpenRouterRequest:
    """Describe one OpenRouter HTTP request before transport dispatch."""

    model: str
    payload: dict[str, object]
    headers: dict[str, str]
    url: str = OPENROUTER_URL
    timeout: float = 60.0


@dataclass(frozen=True, slots=True)
class OpenRouterHTTPResponse:
    """Store the normalized transport response used by the retry loop."""

    status_code: int
    json_body: Mapping[str, object] | None = None
    text_body: str = ""


@dataclass(frozen=True, slots=True)
class OpenRouterToolCall:
    """Store one normalized tool call from an OpenRouter assistant message."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class OpenRouterMessage:
    """Store one normalized assistant message returned by OpenRouter."""

    role: str
    content: str
    tool_calls: tuple[OpenRouterToolCall, ...] = ()


@dataclass(frozen=True, slots=True)
class OpenRouterResponse:
    """Store the first usable OpenRouter completion and its raw payload."""

    model: str
    message: OpenRouterMessage
    finish_reason: str | None = None
    raw: Mapping[str, object] | None = None


OpenRouterRequester = Callable[[OpenRouterRequest], Awaitable[OpenRouterHTTPResponse]]


class OpenRouterClient:
    """Call OpenRouter chat completions with retries, fallback, and safe errors."""

    def __init__(
        self,
        api_key: str,
        *,
        requester: OpenRouterRequester | None = None,
        sleep: SleepHook = asyncio.sleep,
        backoff: BackoffHook | None = None,
        max_attempts: int = 3,
        url: str = OPENROUTER_URL,
        referer: str = "http://localhost",
        title: str = "MCP Host CLI",
        timeout: float = 60.0,
    ) -> None:
        """Configure one OpenRouter client instance for repeated chat calls."""

        self.api_key = api_key
        self._requester = requester or _default_request
        self._sleep = sleep
        self._backoff = backoff or _default_backoff
        self.max_attempts = max(1, max_attempts)
        self.url = url
        self.referer = referer
        self.title = title
        self.timeout = timeout

    async def complete(
        self,
        messages: Sequence[Mapping[str, object]],
        models: Sequence[str],
        *,
        tools: Sequence[Mapping[str, object]] | None = None,
        use_tools: bool = False,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        temperature: float = DEFAULT_TEMPERATURE,
    ) -> OpenRouterResponse:
        """Return the first usable completion across the configured model list."""

        if not self.api_key.strip():
            raise OpenRouterError("Missing OpenRouter API key.")

        model_list = [model for model in models if model]
        if not model_list:
            raise OpenRouterError("No OpenRouter models configured.")

        message_payload = [dict(message) for message in messages]
        tool_payload = [dict(tool) for tool in tools or ()]
        last_error = ""
        saw_rate_limit = False

        for model in model_list:
            for attempt in range(1, self.max_attempts + 1):
                openrouter_request = OpenRouterRequest(
                    model=model,
                    payload=build_openrouter_payload(
                        model,
                        message_payload,
                        tools=tool_payload,
                        use_tools=use_tools,
                        max_tokens=max_tokens,
                        temperature=temperature,
                    ),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                        "HTTP-Referer": self.referer,
                        "X-Title": self.title,
                    },
                    url=self.url,
                    timeout=self.timeout,
                )

                try:
                    response = await self._requester(openrouter_request)
                except Exception as exc:  # pragma: no cover - exercised via tests with fakes.
                    raw_error = str(exc)
                    if _looks_like_rate_limit(raw_error):
                        saw_rate_limit = True
                        last_error = "OpenRouter rate limited. Try again soon."
                        await self._sleep(self._backoff(attempt))
                        continue
                    last_error = _sanitize_error_text(raw_error, api_key=self.api_key)
                    break

                if response.status_code == 429:
                    saw_rate_limit = True
                    last_error = "OpenRouter rate limited. Try again soon."
                    await self._sleep(self._backoff(attempt))
                    continue

                if response.status_code < 200 or response.status_code >= 300:
                    last_error = _safe_http_error(
                        response.status_code,
                        response.text_body,
                        api_key=self.api_key,
                    )
                    break

                try:
                    normalized = normalize_openrouter_response(
                        response.json_body,
                        fallback_model=model,
                    )
                except OpenRouterError as exc:
                    last_error = str(exc)
                    break

                if _should_fallback_for_text_tool_use(
                    normalized,
                    use_tools=use_tools,
                    tools=tool_payload,
                ):
                    last_error = "Model returned tool text instead of tool calls."
                    break

                return normalized

        if saw_rate_limit and not last_error:
            raise OpenRouterError("OpenRouter rate limited. Try again soon.")
        raise OpenRouterError(last_error or "All OpenRouter models failed.")


def build_openrouter_payload(
    model: str,
    messages: Sequence[Mapping[str, object]],
    *,
    tools: Sequence[Mapping[str, object]] | None = None,
    use_tools: bool = False,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    temperature: float = DEFAULT_TEMPERATURE,
) -> dict[str, object]:
    """Build one OpenRouter chat payload with optional tool metadata."""

    payload: dict[str, object] = {
        "model": model,
        "messages": [dict(message) for message in messages],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if use_tools and tools:
        payload["tools"] = [dict(tool) for tool in tools]
        payload["tool_choice"] = "auto"
    return payload


def normalize_openrouter_response(
    payload: Mapping[str, object] | None,
    *,
    fallback_model: str,
) -> OpenRouterResponse:
    """Normalize the first OpenRouter choice into stable dataclasses."""

    if not isinstance(payload, Mapping):
        raise OpenRouterError("OpenRouter returned an invalid response.")

    choices = payload.get("choices")
    if not isinstance(choices, Sequence) or isinstance(choices, (str, bytes, bytearray)):
        raise OpenRouterError("OpenRouter returned an invalid response.")
    if not choices:
        raise OpenRouterError("OpenRouter returned an empty response.")

    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        raise OpenRouterError("OpenRouter returned an invalid response.")

    message_payload = first_choice.get("message")
    if not isinstance(message_payload, Mapping):
        raise OpenRouterError("OpenRouter returned an invalid response.")

    message = OpenRouterMessage(
        role=_string_value(message_payload.get("role"), default="assistant"),
        content=_normalize_content(message_payload.get("content")),
        tool_calls=_normalize_tool_calls(message_payload.get("tool_calls")),
    )
    return OpenRouterResponse(
        model=_string_value(payload.get("model"), default=fallback_model),
        message=message,
        finish_reason=_optional_string_value(first_choice.get("finish_reason")),
        raw=dict(payload),
    )


def content_has_tool_text_marker(content: str | None) -> bool:
    """Return whether text matches the legacy JS tool-use marker heuristic."""

    if not content:
        return False
    return any(marker in content for marker in _TOOL_TEXT_MARKERS)


def extract_javascript_code(content: str | None) -> str | None:
    """Extract a fenced JavaScript block or an export-default script body."""

    if not content:
        return None
    match = _JAVASCRIPT_BLOCK_RE.search(content)
    if match:
        return match.group(1).strip()
    if "export default" in content:
        return content[content.index("export default") :].strip()
    return None


async def _default_request(openrouter_request: OpenRouterRequest) -> OpenRouterHTTPResponse:
    """Send one OpenRouter request with stdlib HTTP primitives."""

    return await asyncio.to_thread(_send_request_sync, openrouter_request)


def _send_request_sync(openrouter_request: OpenRouterRequest) -> OpenRouterHTTPResponse:
    encoded_payload = json.dumps(openrouter_request.payload).encode("utf-8")
    http_request = request.Request(
        openrouter_request.url,
        data=encoded_payload,
        method="POST",
    )
    for header_name, header_value in openrouter_request.headers.items():
        http_request.add_header(header_name, header_value)

    try:
        with request.urlopen(http_request, timeout=openrouter_request.timeout) as response:
            text_body = response.read().decode("utf-8", errors="replace")
            return OpenRouterHTTPResponse(
                status_code=response.getcode() or 200,
                json_body=_parse_json_body(text_body),
                text_body=text_body,
            )
    except error.HTTPError as exc:
        text_body = exc.read().decode("utf-8", errors="replace")
        return OpenRouterHTTPResponse(
            status_code=exc.code,
            json_body=_parse_json_body(text_body),
            text_body=text_body,
        )
    except error.URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def _parse_json_body(text_body: str) -> Mapping[str, object] | None:
    if not text_body:
        return None
    try:
        parsed = json.loads(text_body)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, Mapping):
        return dict(parsed)
    return None


def _default_backoff(attempt: int) -> float:
    return float(10 * attempt)


def _should_fallback_for_text_tool_use(
    response: OpenRouterResponse,
    *,
    use_tools: bool,
    tools: Sequence[Mapping[str, object]],
) -> bool:
    if not use_tools or not tools or response.message.tool_calls:
        return False
    content = response.message.content
    return content_has_tool_text_marker(content) or extract_javascript_code(content) is not None


def _normalize_content(content: object) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, Sequence) and not isinstance(content, (str, bytes, bytearray)):
        blocks: list[str] = []
        for block in content:
            if isinstance(block, Mapping):
                if _string_value(block.get("type")) == "text":
                    blocks.append(_string_value(block.get("text")))
                    continue
                blocks.append(json.dumps(dict(block), ensure_ascii=False, sort_keys=True))
                continue
            blocks.append(_string_value(block))
        return "\n".join(part for part in blocks if part)
    return _string_value(content)


def _normalize_tool_calls(tool_calls: object) -> tuple[OpenRouterToolCall, ...]:
    if not isinstance(tool_calls, Sequence) or isinstance(tool_calls, (str, bytes, bytearray)):
        return ()

    normalized: list[OpenRouterToolCall] = []
    for index, item in enumerate(tool_calls, start=1):
        if not isinstance(item, Mapping):
            continue
        function_payload = item.get("function")
        if isinstance(function_payload, Mapping):
            name = _string_value(function_payload.get("name"))
            arguments = _stringify_json_value(function_payload.get("arguments"))
        else:
            name = _string_value(item.get("name"))
            arguments = _stringify_json_value(item.get("arguments"))
        if not name:
            continue
        normalized.append(
            OpenRouterToolCall(
                id=_string_value(item.get("id"), default=f"tool_call_{index}"),
                name=name,
                arguments=arguments,
            )
        )
    return tuple(normalized)


def _stringify_json_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    if isinstance(value, Mapping):
        return json.dumps(dict(value), ensure_ascii=False, sort_keys=True)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return json.dumps(list(value), ensure_ascii=False)
    return str(value)


def _string_value(value: object, *, default: str = "") -> str:
    if value is None:
        return default
    if isinstance(value, str):
        return value
    return str(value)


def _optional_string_value(value: object) -> str | None:
    if value is None:
        return None
    return _string_value(value)


def _safe_http_error(status_code: int, text_body: str, *, api_key: str) -> str:
    if status_code == 429:
        return "OpenRouter rate limited. Try again soon."

    detail = _sanitize_error_text(text_body, api_key=api_key)
    if detail == "OpenRouter request failed.":
        return detail
    if detail.startswith(str(status_code)):
        return detail
    if detail:
        return f"{status_code} {detail}"
    return "OpenRouter request failed."


def _sanitize_error_text(text: str, *, api_key: str) -> str:
    sanitized = text.strip()
    if api_key:
        sanitized = sanitized.replace(api_key, "[redacted]")
    if _KEYLIKE_TOKEN_RE.search(sanitized):
        return "OpenRouter request failed."
    sanitized = _AUTHORIZATION_RE.sub("credentials redacted", sanitized)
    sanitized = _QUOTED_AUTHORIZATION_RE.sub('"Authorization": "[redacted]"', sanitized)
    sanitized = _BEARER_TOKEN_RE.sub("[redacted]", sanitized)
    sanitized = re.sub(r"\s+", " ", sanitized).strip()

    if not sanitized:
        return "OpenRouter request failed."
    if _SECRET_WORD_RE.search(sanitized):
        return "OpenRouter request failed."
    if len(sanitized) > 120:
        sanitized = sanitized[:117].rstrip() + "..."
    return sanitized


def _looks_like_rate_limit(text: str) -> bool:
    return "429" in text


__all__ = [
    "DEFAULT_MAX_TOKENS",
    "DEFAULT_TEMPERATURE",
    "OPENROUTER_URL",
    "OpenRouterClient",
    "OpenRouterError",
    "OpenRouterHTTPResponse",
    "OpenRouterMessage",
    "OpenRouterRequest",
    "OpenRouterResponse",
    "OpenRouterToolCall",
    "build_openrouter_payload",
    "content_has_tool_text_marker",
    "extract_javascript_code",
    "normalize_openrouter_response",
]