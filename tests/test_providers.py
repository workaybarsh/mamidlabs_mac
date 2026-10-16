"""Provider table and OpenAI <-> Claude converters."""

from __future__ import annotations

import json

import pytest

from mamidlabs.core import providers
from mamidlabs.core.paths import Paths
from mamidlabs.core.settings import SecretStore, Settings


def _settings(tmp_path):
    secrets = SecretStore()
    secrets._keyring = None
    secrets.backend = "file"
    return Settings(Paths(tmp_path), secrets=secrets)


def test_provider_ids():
    assert providers.provider_ids() == ["openai", "claude", "gemini", "deepseek", "custom"]


def test_deepseek_has_no_vision():
    assert providers.get_provider("deepseek").vision is False
    assert providers.get_provider("openai").vision is True


def test_custom_endpoint_requires_base_url(tmp_path):
    settings = _settings(tmp_path)
    with pytest.raises(ValueError):
        providers.endpoint_for("custom", settings)
    settings.provider("custom")["baseUrl"] = "http://localhost:11434/v1/"
    assert providers.endpoint_for("custom", settings) == "http://localhost:11434/v1/chat/completions"


def test_auth_headers():
    assert providers.auth_headers("claude", "k") == {"x-api-key": "k",
                                                     "anthropic-version": "2023-06-01"}
    assert providers.auth_headers("openai", "k") == {"Authorization": "Bearer k"}
    assert providers.auth_headers("custom", "") == {}


def test_to_text_only_flattens_images():
    messages = [{"role": "user", "content": [
        {"type": "text", "text": "bak"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}}]}]
    out = providers.to_text_only(messages)
    assert isinstance(out[0]["content"], str)
    assert "bak" in out[0]["content"]
    assert "görsel" in out[0]["content"]


def test_convert_request_openai(tmp_path):
    settings = _settings(tmp_path)
    body = {"model": "gpt-x", "messages": [{"role": "user", "content": "hi"}], "max_tokens": 100}
    request = providers.convert_request(body, "openai")
    assert request["stream"] is True
    assert request["stream_options"] == {"include_usage": True}
    assert request["max_completion_tokens"] == 100
    assert "max_tokens" not in request


def test_convert_request_deepseek_strips_images():
    body = {"model": "deepseek-chat", "messages": [
        {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "x"}}]}],
        "max_tokens": 50}
    request = providers.convert_request(body, "deepseek")
    assert isinstance(request["messages"][0]["content"], str)


def test_convert_request_claude_system_and_tools():
    body = {"model": "claude-x", "max_tokens": 100, "tool_choice": "auto",
            "messages": [{"role": "system", "content": "sys"},
                         {"role": "user", "content": "hi"}],
            "tools": [{"type": "function", "function": {"name": "f", "description": "d",
                                                        "parameters": {"type": "object"}}}]}
    request = providers.convert_request(body, "claude")
    assert request["system"] == "sys"
    assert request["max_tokens"] == 16000  # floor
    assert request["messages"][0]["role"] == "user"
    assert request["tools"][0]["name"] == "f"
    # Forced tool choice is downgraded to "auto" for Claude.
    assert request["tool_choice"] == {"type": "auto"}


def test_convert_request_claude_tool_result():
    body = {"model": "claude-x", "max_tokens": 100, "messages": [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "t1", "function": {"name": "f", "arguments": json.dumps({"a": 1})}}]},
        {"role": "tool", "tool_call_id": "t1", "content": "result"}]}
    request = providers.convert_request(body, "claude")
    assert request["messages"][0]["content"][0]["type"] == "tool_use"
    assert request["messages"][1]["content"][0] == {"type": "tool_result",
                                                    "tool_use_id": "t1", "content": "result"}


def test_claude_stream_text_and_replay():
    state = providers.ClaudeStream()
    assert state.feed({"type": "content_block_delta", "index": 0,
                       "delta": {"type": "text_delta", "text": "hi"}})["choices"][0]["delta"] == {
        "content": "hi"}
    # A tool_use with a preceding thinking block is recorded for replay.
    state.feed({"type": "content_block_start", "index": 0,
                "content_block": {"type": "thinking", "thinking": "t", "signature": "s"}})
    state.feed({"type": "content_block_start", "index": 1,
                "content_block": {"type": "tool_use", "id": "tu1", "name": "f"}})
    state.feed({"type": "content_block_delta", "index": 1,
                "delta": {"type": "input_json_delta", "partial_json": '{"a":1}'}})
    state.feed({"type": "message_stop"})
    assert "tu1" in state.replay
    assert state.replay["tu1"][0]["type"] == "thinking"


def test_claude_stream_message_delta_usage():
    state = providers.ClaudeStream()
    out = state.feed({"type": "message_delta", "usage": {"output_tokens": 7},
                      "delta": {"stop_reason": "end_turn"}})
    assert out["choices"][0]["finish_reason"] == "stop"
    assert out["usage"]["completion_tokens"] == 7
