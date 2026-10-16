"""User settings (``<root>/settings/api.json``) and secret storage.

On Windows the API keys are encrypted with DPAPI, which is bound to the user
account. macOS has no equivalent single API, so this module uses the login
keychain through the optional ``keyring`` package when it is available and
falls back to storing keys in the settings file itself (which is always written
with ``0600`` permissions). The mode actually in use is exposed as
:attr:`Settings.secret_backend` so the UI can tell the user the truth.

The file is the single source of truth and is written atomically (temp file +
``os.replace``) so a crash can never leave a half-written settings file.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Iterable

from . import i18n
from .paths import Paths

#: Keyring service name used when the OS keyring is available.
KEYRING_SERVICE = "mamidlabs"

#: The defaults every install starts from. Keys mirror the Windows edition so
#: the two editions can share a settings file shape (and so docs stay valid).
DEFAULTS: dict[str, Any] = {
    "selected": "local",
    "selectedModel": "",
    "selectedLocalModel": "builtin-max",
    "localProfile": "max",
    "providers": {},
    "localModels": [],
    "imageLocalModel": "",
    "videoLocalModel": "",
    "imageProvider": "local",
    "videoProvider": "local",
    "externalMediaModels": [],
    "uiPreferences": {"internet": True, "agent": True, "accessMode": False},
    "firstRunApiSettings": False,
    "liteModel": "",
    "liteContext": 32768,
    # ComfyUI is a per-job process by default: it runs only while generating and
    # is closed before the language model loads (keeps idle VRAM/RAM free).
    "comfyKeepAlive": False,
    # Non-speech sound events (AST) are appended to transcripts by default.
    "audioEvents": True,
    # MTP (speculative decoding) is on unless the user disables it.
    "mtp": True,
    "theme": "system",
    # Interface language chosen in the setup wizard (tr | en). The app reads it
    # on start; changing it in the menu writes it back and retranslates live.
    "language": i18n.DEFAULT_LANGUAGE,
}


def _merge(base: dict, incoming: dict) -> dict:
    """Recursively overlay ``incoming`` onto a copy of ``base``."""
    out = dict(base)
    for key, value in incoming.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _merge(out[key], value)
        else:
            out[key] = value
    return out


class SecretStore:
    """Best-effort secret storage.

    Returns the backend name via :attr:`backend`: ``"keyring"`` when the macOS
    login keychain is usable, otherwise ``"file"``. Failures from the keyring are
    never fatal; they fall back to the settings file.
    """

    def __init__(self) -> None:
        self._keyring = None
        self.backend = "file"
        try:  # pragma: no cover - depends on the host's secret service
            import keyring  # type: ignore

            keyring.get_password(KEYRING_SERVICE, "__probe__")
            self._keyring = keyring
            self.backend = "keyring"
        except Exception:
            self._keyring = None
            self.backend = "file"

    def get(self, provider: str) -> str:
        if self._keyring is not None:
            try:  # pragma: no cover - host dependent
                value = self._keyring.get_password(KEYRING_SERVICE, provider)
                if value:
                    return value
            except Exception:
                pass
        return ""

    def set(self, provider: str, value: str) -> None:
        if self._keyring is not None:
            try:  # pragma: no cover - host dependent
                if value:
                    self._keyring.set_password(KEYRING_SERVICE, provider, value)
                else:
                    try:
                        self._keyring.delete_password(KEYRING_SERVICE, provider)
                    except Exception:
                        pass
                return
            except Exception:
                pass
        # fall back to the settings file: nothing else to do here


class Settings:
    """A dict-like settings store backed by a JSON file."""

    def __init__(self, paths: Paths, secrets: SecretStore | None = None) -> None:
        self.paths = paths
        self.secrets = secrets or SecretStore()
        self._data: dict[str, Any] = dict(DEFAULTS)
        self.load()

    # --- persistence -----------------------------------------------------------
    def load(self) -> None:
        path = self.paths.settings_file
        raw: dict[str, Any] = {}
        if path.exists():
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
        self._data = _merge(DEFAULTS, raw if isinstance(raw, dict) else {})

    def save(self) -> None:
        self.paths.settings_dir.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self._data, ensure_ascii=False, indent=2)
        # Atomic write, then tighten permissions (secrets may live here).
        fd, tmp = tempfile.mkstemp(dir=str(self.paths.settings_dir), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
                handle.write(payload)
            os.replace(tmp, self.paths.settings_file)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        try:
            os.chmod(self.paths.settings_file, 0o600)
        except OSError:
            pass

    # --- mapping ---------------------------------------------------------------
    def __getitem__(self, key: str) -> Any:
        return self._data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, DEFAULTS.get(key, default))

    def update(self, values: dict[str, Any]) -> None:
        self._data.update(values)

    def as_dict(self) -> dict[str, Any]:
        return dict(self._data)

    def keys(self) -> Iterable[str]:
        return self._data.keys()

    # --- typed helpers ---------------------------------------------------------
    @property
    def local_profile(self) -> str:
        value = str(self._data.get("localProfile") or "max").lower()
        return value if value in ("max", "flash", "lite") else "max"

    @local_profile.setter
    def local_profile(self, value: str) -> None:
        self._data["localProfile"] = value

    @property
    def language(self) -> str:
        """Interface language code (always a supported one)."""
        return i18n.normalize(str(self._data.get("language") or i18n.DEFAULT_LANGUAGE))

    @language.setter
    def language(self, value: str) -> None:
        self._data["language"] = i18n.normalize(value)

    @property
    def secret_backend(self) -> str:
        return self.secrets.backend

    # --- providers -------------------------------------------------------------
    def provider(self, provider_id: str) -> dict[str, Any]:
        providers = self._data.setdefault("providers", {})
        return providers.setdefault(provider_id, {})

    def provider_key(self, provider_id: str) -> str:
        stored = str(self.provider(provider_id).get("key") or "")
        if stored:
            return stored
        return self.secrets.get(provider_id)

    def set_provider_key(self, provider_id: str, value: str) -> None:
        # Always keep the settings-file copy in sync; keyring (when present) is
        # consulted first on read.
        self.provider(provider_id)["key"] = value
        self.secrets.set(provider_id, value)
