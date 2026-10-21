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
  assistant ``tool_calls`` / ``tool`` pairing stays valid),
* **untrusted content** read this turn (web page, document, OCR, bound file,
  folder search) is labelled as *data* for the model, and writing a file or
  running a command then always asks the user — even with the "full access"
  chip on (prompt-injection defence),
* on MAX/FLASH the reasoning effort is picked **once per turn** from the
  question's difficulty and sent as ``chat_template_kwargs.reasoning_effort``,
  so switching MAX ↔ FLASH no longer has to reload the model.
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

#: Sources whose content is *data*, never a user instruction. Their results are
#: labelled as untrusted and, if any was read this turn, the guarded tools below
#: ask for approval even when the "full access" chip is on.
UNTRUSTED_TOOLS = frozenset({
    "search_web", "fetch_page", "read_document", "read_images_ocr",
    "read_bound_file", "search_folder",
})

#: Tools that must be confirmed when untrusted content was read this turn.
GUARDED_TOOLS = frozenset({"run_command", "write_bound_file"})


def system_prompt() -> str:
    """The fixed system prompt in the current interface language.

    The prompt is deliberately stable within a turn (KV-cache prefix); it only
    changes when the user switches the interface language. English is the source
    text; Turkish comes from ``locales/tr.json``.
    """
    return i18n.t("prompt.system") + "\n" + i18n.t("prompt.untrusted")


#: English source prompt, kept for reference; ``run_turn`` resolves the live
#: value from the catalog so the language can change at runtime.
SYSTEM_PROMPT = system_prompt()


def untrusted_prefix() -> str:
    """Label prepended to every untrusted tool result (web/document/OCR/file)."""
    return i18n.t("chat.untrusted_prefix")


def approval_required(tool_name: str, *, untrusted_read: bool, access_full: bool) -> bool:
    """Whether ``tool_name`` must be confirmed this turn.

    With untrusted content read, the guarded tools ask even under full access:
    a page that hides "run this command" must not be mistaken for the user.
    """
    if untrusted_read and tool_name in GUARDED_TOOLS:
        return True
    return not access_full


# --- auto reasoning effort (MAX/FLASH) ---------------------------------------
#: Turkish letters folded to ASCII so keyword matching is reliable.
_TR_FOLD = str.maketrans({
    "ı": "i", "ü": "u", "ş": "s", "ç": "c", "ö": "o", "ğ": "g", "â": "a", "î": "i",
})

_AUTO_HARD_RE = re.compile(
    r"\b(kanitla|ispat|turet|turev|integral|denklem|matris|olasilik|algoritma|"
    r"hata ayikla|refactor|optimiz|analiz|karsilastir|adim adim|mimari|neden|nicin|"
    r"acikla|proof|prove|derive|equation|algorithm|debug|analy[sz]e|compare|"
    r"step by step|implement|architecture)\b")
_AUTO_CODE_RE = re.compile(
    r"(?m)^\s*```|\b(function|class|def|import|select|const|let|var)\b|[=<>≤≥∑∫√^]")
_AUTO_GREETING_RE = re.compile(
    r"^\s*(merhaba|selam|gunaydin|iyi aksamlar|tesekkur|sagol|hello|hi|thanks|"
    r"good morning)\b")


def auto_reasoning_effort(text: str) -> str:
    """Pick ``low``/``medium``/``xhigh`` for one turn's question (MAX/FLASH).

    MAX and FLASH are the same model; only the server's ``--reasoning-effort``
    differs. Choosing it per request avoids reloading the model (~15 s). The
    choice is made **once per turn** and stays fixed so the system prefix (and
    thus the KV cache) never changes mid-turn.
    """
    if not text or not text.strip():
        return "low"
    folded = text.lower().translate(_TR_FOLD)
    score = 0
    length = len(text)
    if length >= 600:
        score += 2
    elif length >= 220:
        score += 1
    # Multi-step work: maths, proof, code, analysis, architecture, comparison.
    if _AUTO_HARD_RE.search(folded):
        score += 2
    # Code, formula or maths symbols.
    if _AUTO_CODE_RE.search(text):
        score += 2
    if text.count("\n") >= 5:
        score += 1
    if text.count("?") >= 2:
        score += 1
    # Short greetings/thanks should be answered quickly.
    if _AUTO_GREETING_RE.search(folded):
        score -= 3
    if score >= 4:
        return "xhigh"
    if score >= 2:
        return "medium"
    return "low"


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
    """Drop bare 'Source: <url>' lines that appear when the web failed."""
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
    """Shorten old content when the prompt would overflow the context.

    Two passes, mirroring the Windows worker: first only the *head* of the
    oldest tool outputs is kept (most of the value is at the top), and if the
    prompt still does not fit the oldest tool outputs and old assistant text are
    replaced with a short marker. Messages are never removed, so the
    ``assistant.tool_calls`` / ``tool`` pairing stays valid and the server keeps
    accepting the request.

    Returns ``(messages, compacted)``; ``compacted`` is True only when something
    was actually shortened (the status note must not lie).
    """
    budget = max(256, context_limit - max_tokens - CONTEXT_SAFETY_MARGIN)
    if estimate_tokens(messages) <= budget:
        return messages, False
    result = [dict(m) for m in messages]
    trimmed = 0
    # 1) Keep only the head of the oldest tool outputs.
    for index, message in enumerate(result):
        if index == 0:
            continue
        if estimate_tokens(result) <= budget:
            break
        if message.get("role") != "tool":
            continue
        content = message.get("content")
        if isinstance(content, str) and len(content) > 800:
            message["content"] = content[:800] + i18n.t("chat.truncated")
            trimmed += 1
    # 2) Still over budget: replace the oldest tool outputs and old assistant
    #    text with a short marker (``tool_calls`` is preserved).
    marker = i18n.t("chat.trimmed")
    for index, message in enumerate(result):
        if index == 0:
            continue
        if estimate_tokens(result) <= budget:
            break
        if message.get("role") not in ("tool", "assistant"):
            continue
        content = message.get("content")
        if isinstance(content, str) and len(content) > len(marker):
            message["content"] = marker
            trimmed += 1
    return result, trimmed > 0


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
                 reasoning_effort: str | None = None,
                 claude_state: providers.ClaudeStream | None = None,
                 replay: dict | None = None) -> Iterator[dict]:
        """Stream one completion, yielding UI events and ending with a private
        ``{"kind": "_result"}`` carrying the accumulated :class:`TurnResult`."""
        body: dict = {"model": model or "local", "messages": messages, "stream": True,
                      "max_tokens": max_tokens, "temperature": 0.7}
        if tool_defs:
            body["tools"] = tool_defs
            body["tool_choice"] = "auto"
        # Auto effort is a local-server feature (MAX/FLASH share the same model,
        # so the effort is picked per request instead of reloading). LITE's
        # template ignores the key; API providers never receive it.
        if reasoning_effort and provider in ("", "local"):
            body["chat_template_kwargs"] = {"reasoning_effort": reasoning_effort}
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
                 approve: Callable[[str, dict, str], bool] | None = None,
                 system_prompt: str = SYSTEM_PROMPT) -> Iterator[dict]:
        chips = chips or {}
        access_full = bool(chips.get("accessMode", False))
        message_text = _last_user_text(history)
        context_limit = int(self.settings.get("contextLimit", 32768) or 32768)
        web = tools.WebTracker()
        claude_state = providers.ClaudeStream() if provider == "claude" else None
        messages = build_job_messages(system_prompt, history)
        denied: set[str] = set()
        untrusted_read = False
        final_text = ""

        # MAX and FLASH are the same model; pick the effort once for the whole
        # turn (constant prefix → KV cache intact). LITE ignores the key; API
        # providers never receive it.
        effort: str | None = None
        if (provider in ("", "local") and profile in ("max", "flash")
                and bool(self.settings.get("autoEffort", True))):
            effort = auto_reasoning_effort(message_text)

        for _round in range(MAX_TOOL_ROUNDS):
            # F1: keep the turn inside the context window. Shorten old content;
            # if the prompt still does not fit, stop offering tools and ask for a
            # visible answer from the findings (llama-server runs with
            # --no-context-shift, so an overflowing prompt would be a hard error).
            prompt_tokens = estimate_tokens(messages)
            force_final = False
            if prompt_tokens + max_tokens + CONTEXT_SAFETY_MARGIN > context_limit:
                messages, compacted = compact_turn_messages(messages, context_limit,
                                                            max_tokens)
                prompt_tokens = estimate_tokens(messages)
                if prompt_tokens + 256 + CONTEXT_SAFETY_MARGIN > context_limit:
                    force_final = True
                    yield {"kind": "status", "text": i18n.t("chat.context_full")}
                elif compacted:
                    yield {"kind": "compact", "text": i18n.t("chat.compact")}
            tool_defs = [] if force_final else self.registry.definitions(
                chips=chips, message=message_text, has_documents=has_documents,
                has_audio=has_audio, profile_lite=(profile == "lite"),
                web=web, web_locked=web.should_lock_tools)

            # F2: cap the completion budget to the room left in the context
            # (local/custom endpoints only; remote APIs keep their ceiling).
            send_tokens = max_tokens
            if provider in ("", "local", "custom"):
                send_tokens = min(max_tokens,
                                  max(256, context_limit - prompt_tokens
                                      - CONTEXT_SAFETY_MARGIN))
            # The forced-answer note lives only in the request copy, never in the
            # persistent history (the client prefix must match the server's).
            send_messages = messages
            if force_final:
                send_messages = messages + [{"role": "user",
                                             "content": i18n.t("chat.context_full_note")}]

            result: TurnResult | None = None
            for event in self.complete(send_messages, provider=provider, model=model,
                                       tool_defs=tool_defs, max_tokens=send_tokens,
                                       reasoning_effort=effort,
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
                run_tool = True
                output = ""
                if spec and spec.kind in ("write", "exec"):
                    if name in denied:
                        output = json.dumps({"error": "the user denied this tool."},
                                            ensure_ascii=False)
                        yield {"kind": "denied", "tool": name}
                        run_tool = False
                    elif approval_required(name, untrusted_read=untrusted_read,
                                           access_full=access_full):
                        reason = (i18n.t("chat.approval_untrusted")
                                  if untrusted_read and name in GUARDED_TOOLS else "")
                        if approve and not approve(name, arguments, reason):
                            denied.add(name)
                            output = json.dumps({"error": "the user denied this tool."},
                                                ensure_ascii=False)
                            yield {"kind": "denied", "tool": name}
                            run_tool = False
                if run_tool:
                    yield {"kind": "tool", "tool": name, "arguments": arguments}
                    output = self.registry.call(name, arguments)

                if name in ("search_web", "fetch_page", "find_reference_image"):
                    web.record(output)
                    if web.should_lock_tools:
                        messages.append({"role": "system",
                                         "content": "[System note] Web access could not be "
                                                    "established; stop using the web tools."})
                # Untrusted sources: the model must treat the result as DATA, so
                # the content is clearly labelled and any file write/command this
                # turn then asks for approval (prompt-injection defence).
                if name in UNTRUSTED_TOOLS:
                    untrusted_read = True
                    prefix = untrusted_prefix()
                    if isinstance(output, str) and output and not output.startswith(prefix):
                        output = prefix + "\n" + output
                messages.append({"role": "tool", "tool_call_id": call.get("id", ""),
                                 "name": name, "content": output})
            if web.unavailable:
                yield {"kind": "status", "text": "Web access could not be established; "
                                                 "continuing with the available information."}

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
