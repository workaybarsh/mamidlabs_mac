"""Tool gating: what the model is offered, by chips and turn intent."""

from __future__ import annotations

from mamidlabs.core.paths import Paths
from mamidlabs.core.runner import WorkerRunner
from mamidlabs.core.settings import SecretStore, Settings
from mamidlabs.core.tools import ToolRegistry


def _registry(tmp_path):
    secrets = SecretStore()
    secrets._keyring = None
    secrets.backend = "file"
    settings = Settings(Paths(tmp_path), secrets=secrets)
    return ToolRegistry(Paths(tmp_path), settings, WorkerRunner(Paths(tmp_path), settings))


def _names(registry, **kwargs):
    return [d["function"]["name"] for d in registry.definitions(**kwargs)]


def test_web_tools_require_internet_chip(tmp_path):
    reg = _registry(tmp_path)
    assert "search_web" in _names(reg, chips={"internet": True})
    assert "search_web" not in _names(reg, chips={"internet": False})


def test_web_tools_locked_after_failures(tmp_path):
    reg = _registry(tmp_path)
    assert "search_web" not in _names(reg, chips={"internet": True}, web_locked=True)


def test_production_tools_need_intent(tmp_path):
    reg = _registry(tmp_path)
    plain = _names(reg, chips={"internet": True})
    assert "create_document" not in plain
    assert "generate_image" not in plain
    assert "generate_chart" not in plain
    assert "create_document" in _names(reg, chips={"internet": True}, message="bir rapor oluştur")
    assert "generate_image" in _names(reg, chips={"internet": True}, message="kedi resmi çiz")
    assert "generate_chart" in _names(reg, chips={"internet": True}, message="sütun grafiği çiz")


def test_run_command_only_on_command_intent(tmp_path):
    reg = _registry(tmp_path)
    assert "run_command" not in _names(reg, chips={"internet": True})
    assert "run_command" in _names(reg, chips={"internet": True}, message="terminalde çalıştır")


def test_agent_chip_enables_ask_model_and_bound_files(tmp_path):
    reg = _registry(tmp_path)
    plain = _names(reg, chips={"internet": True, "agent": False})
    assert "ask_model" not in plain
    agent = _names(reg, chips={"internet": True, "agent": True})
    assert "ask_model" in agent
    assert "list_bound_files" in agent


def test_audio_turn_hides_bound_file_tools(tmp_path):
    reg = _registry(tmp_path)
    names = _names(reg, chips={"internet": True, "agent": True}, has_audio=True)
    assert "list_bound_files" not in names
    assert "ask_model" in names


def test_read_document_requires_documents(tmp_path):
    reg = _registry(tmp_path)
    assert "read_document" not in _names(reg, chips={"internet": True})
    assert "read_document" in _names(reg, chips={"internet": True}, has_documents=True)


def test_unknown_tool_returns_error(tmp_path):
    reg = _registry(tmp_path)
    result = reg.call("nope", {})
    assert "bilinmeyen araç" in result
