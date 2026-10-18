"""Auto reasoning effort: per-question low/medium/xhigh for MAX/FLASH.

MAX and FLASH are the same model; only the server's ``--reasoning-effort``
differs. Instead of reloading the model the effort is chosen once per turn and
sent as ``chat_template_kwargs.reasoning_effort`` (local server only).
"""

from __future__ import annotations

import json

from mamidlabs.core.inference import InferenceEngine, auto_reasoning_effort
from mamidlabs.core.paths import Paths
from mamidlabs.core.settings import SecretStore, Settings


class Recorder:
    """Stream stub that remembers every request body it was given."""

    def __init__(self, turns):
        self.turns = turns
        self.bodies: list[dict] = []
        self.calls = 0

    def __call__(self, provider, body, settings, key="", *, claude_state=None, replay=None):
        self.bodies.append(body)
        chunks = self.turns[min(self.calls, len(self.turns) - 1)]
        self.calls += 1
        yield from chunks


class StubRegistry:
    def definitions(self, **kwargs):
        return []

    def get(self, name):
        return None

    def call(self, name, arguments):
        return json.dumps({"ok": True})


def _text_chunk(text):
    return {"choices": [{"delta": {"content": text}}]}


def _settings(tmp_path, **overrides):
    secrets = SecretStore()
    secrets._keyring = None
    secrets.backend = "file"
    settings = Settings(Paths(tmp_path), secrets=secrets)
    for key, value in overrides.items():
        settings[key] = value
    return settings


def _engine(tmp_path, turns, **overrides):
    rec = Recorder(turns)
    engine = InferenceEngine(Paths(tmp_path), _settings(tmp_path, **overrides),
                             StubRegistry(), stream_fn=rec)
    return engine, rec


# --- the scorer --------------------------------------------------------------
def test_greeting_is_low():
    assert auto_reasoning_effort("merhaba") == "low"
    assert auto_reasoning_effort("Selam!") == "low"
    assert auto_reasoning_effort("teşekkürler") == "low"


def test_empty_is_low():
    assert auto_reasoning_effort("") == "low"
    assert auto_reasoning_effort("   ") == "low"


def test_short_simple_question_is_low():
    assert auto_reasoning_effort("Saat kaç?") == "low"


def test_hard_math_and_code_is_xhigh():
    assert auto_reasoning_effort("Bu integrali adım adım ispatla: ∫ x^2 dx") == "xhigh"
    assert auto_reasoning_effort("Bu fonksiyonu refactor et:\n```python\ndef f():\n    pass\n```") == "xhigh"


def test_medium_question():
    assert auto_reasoning_effort("Bu veriyi analiz et") == "medium"


# --- it reaches the request body only when it should -------------------------
def test_complete_sends_effort_for_local(tmp_path):
    engine, rec = _engine(tmp_path, [[_text_chunk("ok")]])
    list(engine.complete([{"role": "user", "content": "hi"}], reasoning_effort="xhigh"))
    assert rec.bodies[0]["chat_template_kwargs"] == {"reasoning_effort": "xhigh"}


def test_complete_omits_effort_for_api_provider(tmp_path):
    engine, rec = _engine(tmp_path, [[_text_chunk("ok")]])
    list(engine.complete([{"role": "user", "content": "hi"}], provider="openai",
                         reasoning_effort="xhigh"))
    assert "chat_template_kwargs" not in rec.bodies[0]


def test_complete_omits_when_no_effort(tmp_path):
    engine, rec = _engine(tmp_path, [[_text_chunk("ok")]])
    list(engine.complete([{"role": "user", "content": "hi"}]))
    assert "chat_template_kwargs" not in rec.bodies[0]


def test_run_turn_picks_effort_once_for_max(tmp_path):
    engine, rec = _engine(tmp_path, [[_text_chunk("ok")]])
    list(engine.run_turn([{"role": "user", "content": "Bu integrali adım adım ispatla: ∫ x^2 dx"}],
                         provider="local", profile="max"))
    assert rec.bodies[0]["chat_template_kwargs"] == {"reasoning_effort": "xhigh"}


def test_run_turn_skips_effort_for_lite(tmp_path):
    # LITE's chat template ignores the key; it must not be sent.
    engine, rec = _engine(tmp_path, [[_text_chunk("ok")]])
    list(engine.run_turn([{"role": "user", "content": "Bu denklemi ispatla"}],
                         provider="local", profile="lite"))
    assert "chat_template_kwargs" not in rec.bodies[0]


def test_run_turn_respects_auto_effort_off(tmp_path):
    engine, rec = _engine(tmp_path, [[_text_chunk("ok")]], autoEffort=False)
    list(engine.run_turn([{"role": "user", "content": "Bu denklemi ispatla"}],
                         provider="local", profile="max"))
    assert "chat_template_kwargs" not in rec.bodies[0]


def test_run_turn_skips_effort_for_api_provider(tmp_path):
    engine, rec = _engine(tmp_path, [[_text_chunk("ok")]])
    list(engine.run_turn([{"role": "user", "content": "Bu denklemi ispatla"}],
                         provider="openai", profile="max"))
    assert "chat_template_kwargs" not in rec.bodies[0]


def test_effort_is_constant_within_a_turn(tmp_path):
    # The choice is made once; every round of the turn carries the same value
    # (a changing prefix would break the KV-cache match).
    engine, rec = _engine(
        tmp_path,
        [[{"choices": [{"delta": {"tool_calls": [
            {"index": 0, "id": "t1", "function": {"name": "search_web",
                                                  "arguments": json.dumps({"query": "x"})}}]}}]}],
         [_text_chunk("bitti")]],
    )
    engine.registry.definitions = lambda **kw: []  # type: ignore[assignment]
    list(engine.run_turn([{"role": "user", "content": "Bu algoritmayı analiz et: O(n^2) ispatla"}],
                         provider="local", profile="flash",
                         chips={"internet": True}))
    efforts = [body.get("chat_template_kwargs", {}).get("reasoning_effort")
               for body in rec.bodies]
    assert len(set(efforts)) == 1
    assert efforts[0] == "xhigh"
