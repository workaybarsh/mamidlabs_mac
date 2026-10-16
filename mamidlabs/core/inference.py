"""The chat engine: streaming, tool calling, approval and honesty guards.

This is the macOS port of the agent loop in ``agent/mamidlabs-inference.ps1``.
It streams from ``llama-server`` (or an API provider), runs the tool loop, asks
for approval before write/execute tools, and applies the same safety behaviour:

* production tools only run when the turn's intent allows it (checked at call
  time, not just when the tool is offered),
* a turn that used the web and got *no* successful result never presents the
  model's text as verified, and fabricated citations are stripped,
* the turn's prompt is estimated each round; when it would overflow the context
  the oldest tool outputs are shortened (messages are never deleted, so the
  assistant ``tool_calls`` / ``tool`` pairing stays valid).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Callable, Iterator

from . import i18n, providers, tools
from .paths import Paths
from .settings import Settings

MAX_TOOL_ROUNDS = 8
DEFAULT_MAX_TOKENS = 8192
CONTEXT_SAFETY_MARGIN = 1024


def system_prompt() -> str:
    """The fixed system prompt in the current interface language.

    The prompt is deliberately stable within a turn (KV-cache prefix); it only
    changes when the user switches the interface language. Turkish is the source
    text; English comes from ``locales/en.json``.
    """
    return i18n.t("prompt.system")


#: Turkish source prompt, kept for reference; ``run_turn`` resolves the live
#: value from the catalog so the language can change at runtime.
SYSTEM_PROMPT = system_prompt()


# --- helpers -----------------------------------------------------------------
def estimate_tokens(messages: list[dict]) -> int:
    """Rough prompt size (chars/3), matching the desktop's estimator."""
    total = 0
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            total += len(content)
        elif isinstance(content, list):
            for part in content:
                total += len(str(part.get("text", "")))
        for call in message.get("tool_calls") or []:
            total += len(json.dumps(call, ensure_ascii=False))
    return total // 3


_FABRICATED_CITATION_RE = re.compile(
    r"(?im)^\s*(?:kaynak|source)\s*:\s*(?:https?://\S+|www\.\S+)\s*$"
)


def strip_fabricated_citations(text: str) -> str:
    """Drop bare 'Kaynak: <url>' lines that appear when the web failed."""
    if not text:
        return text
    return _FABRICATED_CITATION_RE.sub("", text).strip()


def build_job_messages(system_prompt: str, history: list[dict]) -> list[dict]:
    """System prompt + history, with old-turn images replaced by a note."""
    messages = [{"role": "system", "content": system_prompt}]
    for index, message in enumerate(history):
        content = message.get("content")
        if isinstance(content, list) and index < len(history) - 1:
            texts = [str(part.get("text", "")) for part in content if part.get("type") == "text"]
            texts.append(i18n.t("chat.previous_image_note"))
            copy = dict(message)
            copy["content"] = "\n".join(t for t in texts if t)
            messages.append(copy)
        else:
            messages.append(dict(message))
    return messages


def compact_turn_messages(messages: list[dict], context_limit: int,
                          max_tokens: int) -> tuple[list[dict], bool]:
    """Shorten the oldest tool outputs when the prompt would overflow.

    Returns ``(messages, compacted)``. Messages are never removed: the
    ``assistant.tool_calls`` / ``tool`` pairing must stay valid.
    """
    budget = max(256, context_limit - max_tokens - CONTEXT_SAFETY_MARGIN)
    if estimate_tokens(messages) <= budget:
        return messages, False
    result = [dict(m) for m in messages]
    for message in result:
        if message.get("role") != "tool":
            continue
        content = message.get("content")
        if isinstance(content, str) and len(content) > 800:
            message["content"] = content[:800] + i18n.t("chat.truncated")
            if estimate_tokens(result) <= budget:
                return result, True
    return result, True


# --- streaming accumulation --------------------------------------------------
def _merge_tool_deltas(target: list[dict], deltas: list[dict]) -> None:
    for delta in deltas:
        index = int(delta.get("index", 0))
        while len(target) <= index:
            target.append({"id": "", "type": "function",
                           "function": {"name": "", "arguments": ""}})
        entry = target[index]
        if delta.get("id"):
            entry["id"] = delta["id"]
        function = delta.get("function") or {}
        if function.get("name"):
            entry["function"]["name"] = function["name"]
        if function.get("arguments"):
            entry["function"]["arguments"] += function["arguments"]


@dataclass
class TurnResult:
    text: str = ""
    reasoning: str = ""
    tool_calls: list[dict] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    finish_reason: str = ""


class InferenceEngine:
    def __init__(self, paths: Paths, settings: Settings, registry: tools.ToolRegistry,
                 *, stream_fn: Callable | None = None) -> None:
        self.paths = paths
        self.settings = settings
        self.registry = registry
        self._stream = stream_fn or providers.stream_chat

    # --- one completion ------------------------------------------------------
    def complete(self, messages: list[dict], *, provider: str = "local", model: str = "",
                 tool_defs: list[dict] | None = None, max_tokens: int = DEFAULT_MAX_TOKENS,
                 claude_state: providers.ClaudeStream | None = None,
                 replay: dict | None = None) -> Iterator[dict]:
        """Stream one completion, yielding UI events and ending with a private
        ``{"kind": "_result"}`` carrying the accumulated :class:`TurnResult`."""
        body: dict = {"model": model or "local", "messages": messages, "stream": True,
                      "max_tokens": max_tokens, "temperature": 0.7}
        if tool_defs:
            body["tools"] = tool_defs
            body["tool_choice"] = "auto"
        result = TurnResult()
        try:
            for chunk in self._stream(provider, body, self.settings,
                                      self.settings.provider_key(provider) if provider != "local" else "",
                                      claude_state=claude_state, replay=replay):
                if chunk.get("usage"):
                    result.usage = chunk["usage"]
                for choice in chunk.get("choices", []):
                    delta = choice.get("delta") or {}
                    if delta.get("reasoning_content"):
                        result.reasoning += str(delta["reasoning_content"])
                        yield {"kind": "thinking", "text": str(delta["reasoning_content"])}
                    if delta.get("content"):
                        result.text += str(delta["content"])
                        yield {"kind": "answer", "text": str(delta["content"])}
                    if delta.get("tool_calls"):
                        _merge_tool_deltas(result.tool_calls, delta["tool_calls"])
                    if choice.get("finish_reason"):
                        result.finish_reason = str(choice["finish_reason"])
        except Exception as exc:  # noqa: BLE001 - surfaced as an error event
            yield {"kind": "error", "text": f"{type(exc).__name__}: {exc}"}
            return
        yield {"kind": "_result", "result": result}

    # --- full turn -----------------------------------------------------------
    def run_turn(self, history: list[dict], *, chips: dict | None = None,
                 provider: str = "local", model: str = "",
                 profile: str = "max", max_tokens: int = DEFAULT_MAX_TOKENS,
                 has_documents: bool = False, has_audio: bool = False,
                 approve: Callable[[str, dict], bool] | None = None,
                 system_prompt: str = SYSTEM_PROMPT) -> Iterator[dict]:
        chips = chips or {}
        message_text = _last_user_text(history)
        context_limit = int(self.settings.get("contextLimit", 32768) or 32768)
        web = tools.WebTracker()
        claude_state = providers.ClaudeStream() if provider == "claude" else None
        messages = build_job_messages(system_prompt, history)
        denied: set[str] = set()
        final_text = ""

        for _round in range(MAX_TOOL_ROUNDS):
            messages, compacted = compact_turn_messages(messages, context_limit, max_tokens)
            if compacted:
                yield {"kind": "compact", "text": "Bağlam sınırına yaklaşıldı; eski araç "
                                                  "çıktıları kısaltıldı."}
            tool_defs = self.registry.definitions(
                chips=chips, message=message_text, has_documents=has_documents,
                has_audio=has_audio, profile_lite=(profile == "lite"),
                web=web, web_locked=web.should_lock_tools)

            result: TurnResult | None = None
            for event in self.complete(messages, provider=provider, model=model,
                                       tool_defs=tool_defs, max_tokens=max_tokens,
                                       claude_state=claude_state,
                                       replay=(claude_state.replay if claude_state else None)):
                if event["kind"] == "_result":
                    result = event["result"]
                else:
                    yield event
            if result is None:
                return
            final_text = result.text

            if not result.tool_calls:
                break

            messages.append({"role": "assistant", "content": result.text or None,
                             "tool_calls": result.tool_calls})
            for call in result.tool_calls:
                name = call.get("function", {}).get("name", "")
                try:
                    arguments = json.loads(call.get("function", {}).get("arguments") or "{}")
                except ValueError:
                    arguments = {}
                spec = self.registry.get(name)
                if spec and spec.kind in ("write", "exec"):
                    if name in denied:
                        output = json.dumps({"error": "kullanıcı bu aracı reddetti."},
                                            ensure_ascii=False)
                        yield {"kind": "denied", "tool": name}
                    elif approve and not approve(name, arguments):
                        denied.add(name)
                        output = json.dumps({"error": "kullanıcı bu aracı reddetti."},
                                            ensure_ascii=False)
                        yield {"kind": "denied", "tool": name}
                    else:
                        yield {"kind": "tool", "tool": name, "arguments": arguments}
                        output = self.registry.call(name, arguments)
                else:
                    yield {"kind": "tool", "tool": name, "arguments": arguments}
                    output = self.registry.call(name, arguments)

                if name in ("search_web", "fetch_page", "find_reference_image"):
                    web.record(output)
                    if web.should_lock_tools:
                        messages.append({"role": "system",
                                         "content": "[Sistem notu] Web erişimi kurulamadı; "
                                                    "web araçlarını kullanmayı bırak."})
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                 "name": name, "content": output})
            if web.unavailable:
                yield {"kind": "status", "text": "Web erişimi kurulamadı; eldeki bilgilerle "
                                                 "devam ediliyor."}

        text = final_text
        if web.unavailable:
            text = strip_fabricated_citations(text)
            text = web.add_failure_note(text)
        yield {"kind": "done", "text": text, "data": messages[1:],
               "web": {"fail_count": web.fail_count, "success": web.success}}


def _last_user_text(history: list[dict]) -> str:
    for message in reversed(history):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return "\n".join(str(p.get("text", "")) for p in content
                                 if p.get("type") == "text")
    return ""


def run_turn_text(engine: InferenceEngine, history: list[dict], **kwargs) -> str:
    """Convenience wrapper that runs a turn and returns the final text."""
    text = ""
    for event in engine.run_turn(history, **kwargs):
        if event["kind"] == "done":
            text = event["text"]
    return text
