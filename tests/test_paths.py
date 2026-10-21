"""Paths and install-root layout."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from mamidlabs.core import paths as paths_mod
from mamidlabs.core.paths import Paths

MACOS = sys.platform == "darwin"


def test_default_root_respects_env(monkeypatch, tmp_path):
    monkeypatch.setenv("MAMIDLABS_ROOT", str(tmp_path / "root"))
    assert paths_mod.default_root() == (tmp_path / "root").resolve()


@pytest.mark.skipif(MACOS, reason="on macOS XDG is ignored; Library is used")
def test_default_root_respects_xdg(monkeypatch, tmp_path):
    monkeypatch.delenv("MAMIDLABS_ROOT", raising=False)
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "data"))
    assert paths_mod.default_root() == (tmp_path / "data" / "mamidlabs").resolve()


def test_default_root_falls_back_to_home(monkeypatch):
    monkeypatch.delenv("MAMIDLABS_ROOT", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    if MACOS:
        expected = Path.home() / "Library" / "Application Support" / "mamidlabs"
    else:
        expected = Path.home() / ".local" / "share" / "mamidlabs"
    assert paths_mod.default_root() == expected.resolve()


def test_well_known_paths(tmp_path):
    p = Paths(tmp_path)
    assert p.llama_server == tmp_path / "llama.cpp" / paths_mod.LLAMA_BUILD / "llama-server"
    assert p.settings_file == tmp_path / "settings" / "api.json"
    assert p.venv_python("app") == tmp_path / "venv" / "app" / "bin" / "python"
    assert p.output_dir("images") == tmp_path / "outputs" / "images"
    assert p.hf_home == tmp_path / "tools" / "hf-home"


def test_ensure_dirs_creates_only_user_folders(tmp_path):
    p = Paths(tmp_path)
    p.ensure_dirs()
    for created in ("settings", "chats", "logs", "tools", "outputs"):
        assert (tmp_path / created).is_dir()
    # Engine/model folders are never created implicitly.
    assert not (tmp_path / "models").exists()
    assert not (tmp_path / "ComfyUI").exists()
