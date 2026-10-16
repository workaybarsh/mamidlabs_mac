"""Settings store: defaults, merge, atomic write, secrets."""

from __future__ import annotations

import json
import os

from mamidlabs.core.paths import Paths
from mamidlabs.core.settings import DEFAULTS, SecretStore, Settings


def _settings(tmp_path):
    # Force the file backend so tests never touch the host keyring.
    secrets = SecretStore()
    secrets._keyring = None
    secrets.backend = "file"
    return Settings(Paths(tmp_path), secrets=secrets)


def test_defaults_present(tmp_path):
    settings = _settings(tmp_path)
    assert settings.local_profile == "max"
    assert settings.get("comfyKeepAlive") is False
    assert settings.get("audioEvents") is True
    assert settings.get("mtp") is True


def test_merge_preserves_nested_defaults(tmp_path):
    paths = Paths(tmp_path)
    paths.settings_dir.mkdir(parents=True)
    paths.settings_file.write_text(json.dumps({"uiPreferences": {"internet": False}}),
                                  encoding="utf-8")
    settings = Settings(paths, secrets=_settings(tmp_path).secrets)
    assert settings["uiPreferences"]["internet"] is False
    assert settings["uiPreferences"]["agent"] is True  # untouched default


def test_save_is_atomic_and_restrictive(tmp_path):
    settings = _settings(tmp_path)
    settings["localProfile"] = "lite"
    settings.save()
    assert json.loads(settings.paths.settings_file.read_text(encoding="utf-8"))["localProfile"] == "lite"
    if os.name != "nt":
        assert (settings.paths.settings_file.stat().st_mode & 0o777) == 0o600


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    paths = Paths(tmp_path)
    paths.settings_dir.mkdir(parents=True)
    paths.settings_file.write_text("{ not json", encoding="utf-8")
    settings = Settings(paths, secrets=_settings(tmp_path).secrets)
    assert settings.local_profile == DEFAULTS["localProfile"]


def test_provider_key_roundtrip(tmp_path):
    settings = _settings(tmp_path)
    settings.set_provider_key("openai", "sk-test")
    assert settings.provider_key("openai") == "sk-test"
    assert settings.provider("openai")["key"] == "sk-test"


def test_local_profile_validates(tmp_path):
    settings = _settings(tmp_path)
    settings["localProfile"] = "bogus"
    assert settings.local_profile == "max"
