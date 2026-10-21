"""Chat providers: OpenAI, Claude, Gemini, DeepSeek and a custom OpenAI-compatible endpoint.

This is the macOS port of ``agent/api-providers.ps1``. A single table drives the
UI lists, the key page links, and the request/response converters. Adding a
provider means adding a row here; only non-OpenAI-compatible providers (Claude)
need a converter.

``custom`` lets the user point at any OpenAI-compatible endpoint (Ollama, LM
Studio, vLLM, an in-house proxy). Its base URL is read from settings; the key is
optional because most local servers do not authenticate.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .settings import Settings

LOCAL_ENDPOINT = "http://127.0.0.1:8080/v1/chat/completions"


@dataclass(frozen=True)
class Provider:
    id: str
    label: str
    env: str
    endpoint: str
    models_url: str
    key_page: str
    vision: bool = True
    needs_base_url: bool = False


CHAT_PROVIDERS: tuple[Provider, ...] = (
    Provider("openai", "OpenAI", "OPENAI_API_KEY",
             "https://api.openai.com/v1/chat/completions",
             "https://api.openai.com/v1/models",
             "https://platform.openai.com/api-keys"),
    Provider("claude", "Claude", "ANTHROPIC_API_KEY",
             "https://api.anthropic.com/v1/messages",
             "https://api.anthropic.com/v1/models?limit=100",
             "https://console.anthropic.com/settings/keys"),
    Provider("gemini", "Gemini", "GEMINI_API_KEY",
             "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions",
             "https://generativelanguage.googleapis.com/v1beta/openai/models",
             "https://aistudio.google.com/apikey"),
    # DeepSeek is OpenAI-compatible but its chat models reject image input.
    Provider("deepseek", "DeepSeek", "DEEPSEEK_API_KEY",
             "https://api.deepseek.com/chat/completions",
             "https://api.deepseek.com/models",
             "https://platform.deepseek.com/api_keys", vision=False),
    Provider("custom", "Custom (OpenAI-compatible)", "CUSTOM_API_KEY",
             "", "", "", needs_base_url=True),
)

_BY_ID = {p.id: p for p in CHAT_PROVIDERS}


def provider_ids() -> list[str]:
    return [p.id for p in CHAT_PROVIDERS]


def get_provider(provider_id: str) -> Provider | None:
    return _BY_ID.get(provider_id)


def custom_base_url(settings: Settings, override: str = "") -> str:
    base = override or str(settings.provider("custom").get("baseUrl") or "")
    return base.rstrip("/")


def endpoint_for(provider_id: str, settings: Settings, base_url_override: str = "") -> str:
    if provider_id == "custom":
        base = custom_base_url(settings, base_url_override)
        if not base:
            raise ValueError("Enter the base URL for the custom API in the API connections window first.")
        return f"{base}/chat/completions"
    entry = get_provider(provider_id)
    return entry.endpoint if entry else LOCAL_ENDPOINT


def models_url_for(provider_id: str, settings: Settings, base_url_override: str = "") -> str:
    if provider_id == "custom":
        base = custom_base_url(settings, base_url_override)
        if not base:
            raise ValueError("Enter the base URL first.")
        return f"{base}/models"
    entry = get_provider(provider_id)
    if not entry:
        raise ValueError(f"Unknown provider: {provider_id}")
    return entry.models_url


def auth_headers(provider_id: str, key: str) -> dict[str, str]:
    if not key:
        return {}
    if provider_id == "claude":
        return {"x-api-key": key, "anthropic-version": "2023-06-01"}
    return {"Authorization": f"Bearer {key}"}


def _http_json(url: str, headers: dict[str, str], timeout: float = 20.0) -> dict:
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        return json.loads(response.read().decode("utf-8", errors="replace"))


def fetch_models(provider_id: str, key: str, settings: Settings,
                 base_url_override: str = "") -> list[str]:
    """Validate a key against the provider's models endpoint and list chat models."""
    entry = get_provider(provider_id)
    if not entry:
        raise ValueError(f"Unknown provider: {provider_id}")
    if not key and provider_id != "custom":
        raise ValueError("Enter the API key first.")
    url = models_url_for(provider_id, settings, base_url_override)
    try:
        data = _http_json(url, auth_headers(provider_id, key))
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ValueError(f"{entry.label} rejected the key ({exc.code}). Check the key.") from exc
        raise ValueError(f"Could not connect to {entry.label}: {exc}") from exc
    except Exception as exc:  # noqa: BLE001 - surfaced verbatim to the UI
        raise ValueError(f"Could not connect to {entry.label}: {exc}") from exc

    ids = [str(m.get("id", "")).removeprefix("models/") for m in data.get("data", [])]
    ids = [i for i in ids if i]
    if provider_id == "openai":
        ids = [i for i in ids if i.startswith(("gpt", "o", "chatgpt"))
               and not any(t in i.lower() for t in ("audio", "realtime", "transcribe", "tts",
                                                    "image", "search", "embedding"))]
    elif provider_id == "gemini":
        ids = [i for i in ids if i.startswith("gemini")
               and not any(t in i.lower() for t in ("embedding", "image", "tts", "live"))]
    return sorted(set(ids))


def fetch_model_contexts(provider_id: str, key: str, settings: Settings,
                         base_url_override: str = "") -> dict[str, int]:
    """Best-effort context-window discovery from the models endpoint."""
    entry = get_provider(provider_id)
    if not entry or (not key and provider_id != "custom"):
        return {}
    try:
        url = models_url_for(provider_id, settings, base_url_override)
        data = _http_json(url, auth_headers(provider_id, key))
    except Exception:  # noqa: BLE001 - discovery is optional
        return {}
    out: dict[str, int] = {}
    for model in data.get("data", []):
        mid = str(model.get("id", "")).removeprefix("models/")
        if not mid:
            continue
        ctx = 0
        for field_name in ("context_length", "context_window", "max_context_length",
                           "max_input_tokens", "max_context_tokens"):
            value = model.get(field_name)
            if isinstance(value, int) and value > 0:
                ctx = value
                break
        if ctx <= 0 and isinstance(model.get("top_provider"), dict):
            value = model["top_provider"].get("context_length")
            if isinstance(value, int):
                ctx = value
        if ctx > 0:
            out[mid] = ctx
    return out


# --- message conversion ------------------------------------------------------
def plain_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(str(part.get("text", "")) for part in content
                         if isinstance(part, dict) and part.get("type") == "text")
    return "" if content is None else str(content)


def to_text_only(messages: list[dict]) -> list[dict]:
    """Flatten image parts to a note for providers that reject image input."""
    out = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str) or content is None:
            out.append(dict(message))
            continue
        texts = []
        for part in content:
            if part.get("type") == "text":
                texts.append(str(part.get("text", "")))
            elif part.get("type") == "image_url":
                texts.append("[The user attached an image; this provider cannot read images. "
                             "Use the OCR result if needed.]")
        copy = dict(message)
        copy["content"] = "\n".join(texts)
        out.append(copy)
    return out


def _claude_image_block(part: dict) -> dict | None:
    url = str(part.get("image_url", {}).get("url", ""))
    if url.startswith("data:"):
        header, _, data = url.partition(",")
        media_type = header[5:].split(";")[0] or "image/png"
        return {"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}}
    if url:
        return {"type": "image", "source": {"type": "url", "url": url}}
    return None


def convert_request(body: dict, provider_id: str,
                    replay: dict[str, list[dict]] | None = None) -> dict:
    """Convert an OpenAI chat body to the provider's wire format."""
    if not provider_id or provider_id == "local":
        return body
    replay = replay or {}
    if provider_id != "claude":
        entry = get_provider(provider_id)
        request: dict[str, Any] = {"model": body["model"], "stream": True}
        messages = body["messages"]
        if entry and not entry.vision:
            messages = to_text_only(messages)
        request["messages"] = messages
        request["stream_options"] = {"include_usage": True}
        if provider_id == "openai":
            request["max_completion_tokens"] = body.get("max_tokens")
        else:
            request["max_tokens"] = body.get("max_tokens")
        if body.get("tools"):
            request["tools"] = body["tools"]
        if body.get("tool_choice"):
            request["tool_choice"] = body["tool_choice"]
        return request

    # Claude Messages API.
    request = {"model": body["model"], "stream": True,
               "max_tokens": max(int(body.get("max_tokens", 0)), 16000)}
    system_parts: list[str] = []
    messages: list[dict] = []
    for message in body["messages"]:
        role = message.get("role")
        if role in ("system", "developer"):
            system_parts.append(plain_text(message.get("content")))
            continue
        blocks: list[dict] = []
        if role == "tool":
            role = "user"
            blocks.append({"type": "tool_result",
                           "tool_use_id": str(message.get("tool_call_id", "")),
                           "content": str(message.get("content", ""))})
        else:
            content = message.get("content")
            if isinstance(content, str):
                if content:
                    blocks.append({"type": "text", "text": content})
            elif isinstance(content, list):
                for part in content:
                    if part.get("type") == "text":
                        blocks.append({"type": "text", "text": str(part.get("text", ""))})
                    elif part.get("type") == "image_url":
                        block = _claude_image_block(part)
                        if block:
                            blocks.append(block)
            for call in message.get("tool_calls") or []:
                if not call:
                    continue
                fn = call.get("function", {})
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except ValueError:
                    args = {}
                blocks.append({"type": "tool_use", "id": str(call.get("id", "")),
                               "name": str(fn.get("name", "")), "input": args})
            first_tool = next((c for c in (message.get("tool_calls") or []) if c), None)
            if role == "assistant" and first_tool and str(first_tool.get("id")) in replay:
                blocks = list(replay[str(first_tool["id"])])
        if not blocks:
            continue
        if messages and messages[-1]["role"] == role:
            messages[-1]["content"] = list(messages[-1]["content"]) + blocks
        else:
            messages.append({"role": role, "content": blocks})
    request["messages"] = messages
    if system_parts:
        request["system"] = "\n\n".join(system_parts)
    if body.get("tools"):
        request["tools"] = [{"name": t["function"]["name"],
                             "description": t["function"]["description"],
                             "input_schema": t["function"]["parameters"]}
                            for t in body["tools"]]
    # Forced tool choice is rejected while thinking; Claude only ever gets "auto".
    if body.get("tool_choice") and request.get("tools"):
        request["tool_choice"] = {"type": "auto"}
    return request


class ClaudeStream:
    """Normalizes the Claude stream into OpenAI-style chunks.

    While thinking is on, the signed ``thinking`` blocks must be replayed in
    order on the next tool-loop request; they are collected here keyed by the
    first ``tool_use`` id (memory only — never written to disk).
    """

    def __init__(self) -> None:
        self.prompt = 0
        self.completion = 0
        self._blocks: dict[int, dict] = {}
        self._replay: dict[str, list[dict]] = {}

    @property
    def replay(self) -> dict[str, list[dict]]:
        return self._replay

    def feed(self, chunk: dict) -> dict:
        kind = str(chunk.get("type", ""))
        self._collect(chunk)
        out: dict[str, Any] = {"choices": []}
        if kind == "error":
            return {"error": chunk.get("error")}
        if kind == "message_start":
            usage = chunk.get("message", {}).get("usage", {})
            self.prompt = (int(usage.get("input_tokens", 0))
                           + int(usage.get("cache_read_input_tokens", 0))
                           + int(usage.get("cache_creation_input_tokens", 0)))
            self.completion = int(usage.get("output_tokens", 0))
        elif kind == "content_block_start":
            block = chunk.get("content_block", {})
            if block.get("type") == "tool_use":
                out["choices"] = [{"delta": {"tool_calls": [{
                    "index": int(chunk.get("index", 0)), "id": block.get("id"),
                    "function": {"name": block.get("name"), "arguments": ""}}]}}]
        elif kind == "content_block_delta":
            delta_in = chunk.get("delta", {})
            delta: dict[str, Any] = {}
            if delta_in.get("type") == "text_delta":
                delta["content"] = str(delta_in.get("text", ""))
            elif delta_in.get("type") == "thinking_delta":
                delta["reasoning_content"] = str(delta_in.get("thinking", ""))
            elif delta_in.get("type") == "input_json_delta":
                delta["tool_calls"] = [{"index": int(chunk.get("index", 0)),
                                        "function": {"arguments": str(delta_in.get("partial_json", ""))}}]
            out["choices"] = [{"delta": delta}]
        elif kind == "message_delta":
            self.completion = int(chunk.get("usage", {}).get("output_tokens", 0))
            reason = {"max_tokens": "length", "tool_use": "tool_calls"}.get(
                chunk.get("delta", {}).get("stop_reason"), "stop")
            out["choices"] = [{"delta": {}, "finish_reason": reason}]
        elif kind == "message_stop":
            out["providerDone"] = True
        if kind in ("message_start", "message_delta", "message_stop"):
            out["usage"] = {"prompt_tokens": self.prompt, "completion_tokens": self.completion}
        return out

    def _collect(self, chunk: dict) -> None:
        kind = str(chunk.get("type", ""))
        if kind == "content_block_start":
            block = chunk.get("content_block", {})
            index = int(chunk.get("index", 0))
            btype = block.get("type")
            if btype == "thinking":
                self._blocks[index] = {"type": "thinking", "thinking": str(block.get("thinking", "")),
                                       "signature": str(block.get("signature", ""))}
            elif btype == "redacted_thinking":
                self._blocks[index] = {"type": "redacted_thinking", "data": str(block.get("data", ""))}
            elif btype == "text":
                self._blocks[index] = {"type": "text", "text": str(block.get("text", ""))}
            elif btype == "tool_use":
                self._blocks[index] = {"type": "tool_use", "id": str(block.get("id", "")),
                                       "name": str(block.get("name", "")), "json": ""}
        elif kind == "content_block_delta":
            block = self._blocks.get(int(chunk.get("index", 0)))
            if not block:
                return
            delta = chunk.get("delta", {})
            if delta.get("type") == "thinking_delta":
                block["thinking"] += str(delta.get("thinking", ""))
            elif delta.get("type") == "signature_delta":
                block["signature"] = str(delta.get("signature", ""))
            elif delta.get("type") == "text_delta":
                block["text"] += str(delta.get("text", ""))
            elif delta.get("type") == "input_json_delta":
                block["json"] += str(delta.get("partial_json", ""))
        elif kind == "message_stop":
            blocks = [self._blocks[k] for k in sorted(self._blocks)]
            tools = [b for b in blocks if b["type"] == "tool_use"]
            has_thinking = any(b["type"] in ("thinking", "redacted_thinking") for b in blocks)
            if not tools or not has_thinking:
                return
            content: list[dict] = []
            for block in blocks:
                if block["type"] == "tool_use":
                    try:
                        tool_input = json.loads(block["json"] or "{}")
                    except ValueError:
                        return
                    content.append({"type": "tool_use", "id": block["id"],
                                    "name": block["name"], "input": tool_input})
                elif block["type"] != "text" or block["text"]:
                    content.append({k: v for k, v in block.items() if k != "json"})
            self._replay[str(tools[0]["id"])] = content


def convert_chunk(chunk: dict, provider_id: str, state: ClaudeStream) -> dict:
    if provider_id != "claude":
        return chunk
    return state.feed(chunk)


# --- streaming ---------------------------------------------------------------
def _iter_sse(response) -> "Iterator[dict]":
    for raw in response:
        line = raw.decode("utf-8", errors="replace").strip()
        if not line or not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if data == "[DONE]":
            return
        try:
            yield json.loads(data)
        except ValueError:
            continue


def stream_chat(provider_id: str, body: dict, settings: Settings, key: str = "",
                *, base_url_override: str = "", timeout: float = 300.0,
                claude_state: ClaudeStream | None = None,
                replay: dict[str, list[dict]] | None = None):
    """Yield normalized chunks from a provider (or the local server).

    ``provider_id`` of ``""``/``"local"`` targets llama-server on port 8080.
    """
    if provider_id in ("", "local"):
        url = LOCAL_ENDPOINT
        request_body = body
        headers: dict[str, str] = {}
        state = None
    else:
        url = endpoint_for(provider_id, settings, base_url_override)
        state = claude_state if provider_id == "claude" else None
        if provider_id == "claude" and state is None:
            state = ClaudeStream()
        request_body = convert_request(body, provider_id,
                                       replay if replay is not None
                                       else (state.replay if state else None))
        headers = auth_headers(provider_id, key)
    headers["Content-Type"] = "application/json"
    request = urllib.request.Request(  # noqa: S310
        url, data=json.dumps(request_body, ensure_ascii=False).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
        for chunk in _iter_sse(response):
            if "error" in chunk:
                raise RuntimeError(str(chunk["error"]))
            yield convert_chunk(chunk, provider_id, state) if state else chunk


def stream_completion(provider_id: str, body: dict, settings: Settings, key: str = "",
                      *, base_url_override: str = "", timeout: float = 300.0) -> str:
    """Collect a non-streamed-looking completion (used by ``ask_model``)."""
    parts: list[str] = []
    for chunk in stream_chat(provider_id, body, settings, key,
                             base_url_override=base_url_override, timeout=timeout):
        for choice in chunk.get("choices", []):
            content = (choice.get("delta") or {}).get("content")
            if content:
                parts.append(str(content))
    return "".join(parts)

