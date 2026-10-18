"""Chat engine: message building, compaction, tool loop and honesty guards."""

from __future__ import annotations

import json
from dataclasses import dataclass

from mamidlabs.core.inference import (CONTEXT_SAFETY_MARGIN, InferenceEngine,
                                      build_job_messages, compact_turn_messages,
                                      estimate_tokens, strip_fabricated_citations)
from mamidlabs.core.paths import Paths
from mamidlabs.core.settings import SecretStore, Settings


# --- fakes -------------------------------------------------------------------
class FakeStream:
    def __init__(self, turns):
        self.turns = turns
        self.calls = 0

    def __call__(self, provider, body, settings, key="", *, claude_state=None, replay=None):
        chunks = self.turns[min(self.calls, len(self.turns) - 1)]
        self.calls += 1
        yield from chunks


@dataclass
class Spec:
    name: str
    kind: str = "read"


class StubRegistry:
    def __init__(self, specs, results):
        self.specs = {s.name: s for s in specs}
        self.results = results

    def definitions(self, **kwargs):
        return [{"type": "function", "function": {"name": n}} for n in self.specs]

    def get(self, name):
        return self.specs.get(name)

    def call(self, name, arguments):
        return self.results.get(name, json.dumps({"ok": True}))


class RecordingStream(FakeStream):
    """FakeStream that also keeps every request body (to inspect the prompt)."""

    def __init__(self, turns):
        super().__init__(turns)
        self.bodies: list[dict] = []

    def __call__(self, provider, body, settings, key="", *, claude_state=None, replay=None):
        self.bodies.append(body)
        yield from super().__call__(provider, body, settings, key,
                                    claude_state=claude_state, replay=replay)


def _settings(tmp_path):
    secrets = SecretStore()
    secrets._keyring = None
    secrets.backend = "file"
    return Settings(Paths(tmp_path), secrets=secrets)


def _text_chunk(text):
    return {"choices": [{"delta": {"content": text}}]}


def _tool_chunk(name, arguments, call_id="t1"):
    return {"choices": [{"delta": {"tool_calls": [
        {"index": 0, "id": call_id, "function": {"name": name, "arguments": arguments}}]}}]}


def _engine(tmp_path, turns, specs=(), results=None):
    registry = StubRegistry(list(specs), results or {})
    stream = FakeStream(turns)
    return InferenceEngine(Paths(tmp_path), _settings(tmp_path), registry,
                           stream_fn=stream), stream


# --- pure helpers ------------------------------------------------------------
def test_build_job_messages_strips_old_images():
    history = [
        {"role": "user", "content": [{"type": "text", "text": "birinci"},
                                     {"type": "image_url", "image_url": {"url": "x"}}]},
        {"role": "assistant", "content": "tamam"},
        {"role": "user", "content": [{"type": "text", "text": "ikinci"},
                                     {"type": "image_url", "image_url": {"url": "y"}}]},
    ]
    messages = build_job_messages("sys", history)
    assert messages[0]["role"] == "system"
    assert isinstance(messages[1]["content"], str)
    assert "önceki turda" in messages[1]["content"]
    # The last turn keeps its image.
    assert isinstance(messages[3]["content"], list)


def test_compact_turn_messages_shortens_tool_output():
    messages = [{"role": "system", "content": "s"},
                {"role": "tool", "tool_call_id": "t", "content": "x" * 5000}]
    compacted, changed = compact_turn_messages(messages, context_limit=100, max_tokens=50)
    assert changed is True
    assert len(compacted[1]["content"]) < 5000
    assert len(messages) == len(compacted)  # never deletes messages


def test_compact_no_change_when_fits():
    messages = [{"role": "user", "content": "short"}]
    compacted, changed = compact_turn_messages(messages, context_limit=32768, max_tokens=8192)
    assert changed is False
    assert compacted == messages


def test_compact_reports_no_change_when_nothing_shortenable():
    # Over budget but the only message is the user's own (never shortened):
    # the function must not claim it changed anything.
    messages = [{"role": "user", "content": "u" * 40000}]
    compacted, changed = compact_turn_messages(messages, context_limit=4096, max_tokens=1024)
    assert changed is False
    assert compacted == messages


def test_compact_many_tool_outputs_fits_after_marker_pass():
    # Truncating to 800 chars is not enough on its own: the second (marker) pass
    # must bring a long tool-heavy turn under budget without dropping messages.
    messages = [{"role": "system", "content": "s" * 200}]
    for index in range(30):
        messages.append({"role": "assistant", "content": None,
                         "tool_calls": [{"id": f"t{index}", "type": "function",
                                         "function": {"name": "read_bound_file",
                                                      "arguments": "{}"}}]})
        messages.append({"role": "tool", "tool_call_id": f"t{index}",
                         "name": "read_bound_file", "content": "z" * 5000})
    context_limit, max_tokens = 8192, 1024
    budget = max(256, context_limit - max_tokens - CONTEXT_SAFETY_MARGIN)
    compacted, changed = compact_turn_messages(messages, context_limit, max_tokens)
    assert changed is True
    assert estimate_tokens(compacted) <= budget
    assert len(compacted) == len(messages)  # nothing deleted
    ids_calls = [c["id"] for m in compacted for c in (m.get("tool_calls") or [])]
    ids_tools = [m["tool_call_id"] for m in compacted if m.get("role") == "tool"]
    assert ids_calls == ids_tools  # tool_calls / tool pairing stays valid


def test_run_turn_no_compact_event_when_prompt_fits(tmp_path):
    engine, stream = _engine(tmp_path, [[_text_chunk("Merhaba")]])
    events = list(engine.run_turn([{"role": "user", "content": "selam"}]))
    assert [e["kind"] for e in events if e["kind"] == "compact"] == []
    assert stream.calls == 1


def test_run_turn_overflow_forces_final_answer_and_clamps_tokens(tmp_path):
    registry = StubRegistry([Spec("search_web")], {})
    stream = RecordingStream([[_text_chunk("Elimdeki bulgularla: ...")]])
    engine = InferenceEngine(Paths(tmp_path), _settings(tmp_path), registry,
                             stream_fn=stream)
    engine.settings["contextLimit"] = 8192
    history = [{"role": "user", "content": "u" * 40000}]  # cannot be shortened
    events = list(engine.run_turn(history, max_tokens=1024))
    assert any(e["kind"] == "status" and "bağlam" in e["text"].lower()
               for e in events)
    body = stream.bodies[0]
    assert "tools" not in body                 # tools dropped, no overflow error
    assert body["max_tokens"] == 256           # clamped to the remaining room
    note = body["messages"][-1]
    assert note["role"] == "user" and "[Sistem notu]" in note["content"]
    assert events[-1]["kind"] == "done"
    # The forced-answer note lives only in the request copy, not in history.
    assert not any("[Sistem notu]" in str(m.get("content"))
                   for m in events[-1]["data"])


def test_strip_fabricated_citations():
    text = "Yanıt burada.\nKaynak: https://fake.example/x\nSon satır."
    out = strip_fabricated_citations(text)
    assert "https://fake.example" not in out
    assert "Yanıt burada." in out


# --- turn loop ---------------------------------------------------------------
def test_plain_answer(tmp_path):
    engine, _ = _engine(tmp_path, [[_text_chunk("Merhaba")]])
    events = list(engine.run_turn([{"role": "user", "content": "selam"}]))
    done = events[-1]
    assert done["kind"] == "done"
    assert done["text"] == "Merhaba"


def test_web_failure_appends_note(tmp_path):
    engine, stream = _engine(
        tmp_path,
        [[_tool_chunk("search_web", json.dumps({"query": "hava"}))],
         [_text_chunk("Bilemiyorum.")]],
        specs=[Spec("search_web", "read")],
        results={"search_web": json.dumps({"error": "HTTP Error 403: Forbidden"})},
    )
    events = list(engine.run_turn([{"role": "user", "content": "hava nasıl?"}]))
    done = events[-1]
    assert stream.calls == 2
    assert "başarısız" in done["text"]
    assert done["web"]["fail_count"] == 1
    assert done["web"]["success"] is False


def test_partial_web_success_has_no_note(tmp_path):
    # First call succeeds, second fails: this must NOT be reported as a failure.
    engine, stream = _engine(
        tmp_path,
        [[_tool_chunk("search_web", json.dumps({"query": "a"}), "t1")],
         [_tool_chunk("search_web", json.dumps({"query": "b"}), "t2")],
         [_text_chunk("18 derece.")]],
        specs=[Spec("search_web", "read")],
        results={"search_web": json.dumps({"error": "HTTP Error 403"})},
    )
    # Override results per call: first success, then failure.
    results_iter = iter([json.dumps([{"title": "ok"}]), json.dumps({"error": "HTTP Error 403"})])
    engine.registry.call = lambda name, args: next(results_iter)  # type: ignore[assignment]
    events = list(engine.run_turn([{"role": "user", "content": "hava?"}]))
    done = events[-1]
    assert done["web"]["success"] is True
    assert done["web"]["fail_count"] == 1
    assert "başarısız" not in done["text"]
    assert done["text"] == "18 derece."


def test_write_tool_requires_approval_and_denial_is_recorded(tmp_path):
    engine, _ = _engine(
        tmp_path,
        [[_tool_chunk("write_bound_file", json.dumps({"relative_path": "a.txt", "content": "x"}))],
         [_text_chunk("Yazmadım.")]],
        specs=[Spec("write_bound_file", "write")],
    )
    calls = []

    def deny(name, args, reason=""):
        calls.append(name)
        return False

    events = list(engine.run_turn([{"role": "user", "content": "dosya yaz"}], approve=deny))
    assert any(e["kind"] == "denied" for e in events)
    assert calls == ["write_bound_file"]


def test_estimate_tokens_counts_content_and_calls():
    messages = [{"role": "assistant", "content": "x" * 300,
                 "tool_calls": [{"id": "t", "function": {"name": "f", "arguments": "{}"}}]}]
    assert estimate_tokens(messages) >= 100
