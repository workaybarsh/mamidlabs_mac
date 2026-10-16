"""Runtime localisation (TR/ENG) for the unified macOS edition.

The Windows edition was once two separate repositories (``MamidLabsTR`` and
``MamidLabsENG``) that differed only by hardcoded strings and a handful of
localised identifiers. The unified edition keeps **one** codebase and moves every
user-facing string into JSON catalogs under ``mamidlabs/locales``:

    mamidlabs/locales/tr.json
    mamidlabs/locales/en.json

Rules that keep this honest:

* Turkish is the source language. A missing key in ``en.json`` falls back to the
  Turkish string, then to the key itself, so the UI can never render an empty
  label.
* ``set_language`` is process-global (the app has a single UI language) and is
  what the installer/wizard writes into ``settings/api.json:language``.
* The intent keyword lists are deliberately **not** translated at runtime: a user
  may type in either language, so the tool-intent matchers accept both.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

#: Languages the unified edition ships. ``tr`` is the default (source) language.
SUPPORTED = ("tr", "en")

#: Language used when nothing else is configured.
DEFAULT_LANGUAGE = "tr"

#: ``mamidlabs/locales`` sits next to the ``core`` package.
LOCALES_DIR = Path(__file__).resolve().parent.parent / "locales"

_current: str = DEFAULT_LANGUAGE
_catalogs: dict[str, dict[str, str]] = {}


def _load_catalog(code: str) -> dict[str, str]:
    """Read one locale file; a broken/missing file yields an empty catalog."""
    path = LOCALES_DIR / f"{code}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {str(k): str(v) for k, v in data.items()} if isinstance(data, dict) else {}


def _catalog(code: str) -> dict[str, str]:
    if code not in _catalogs:
        _catalogs[code] = _load_catalog(code)
    return _catalogs[code]


def available() -> tuple[str, ...]:
    return SUPPORTED


#: Human-readable language names seen in installers/env vars.
_ALIASES = {
    "turkish": "tr", "türkçe": "tr", "turkce": "tr", "tr_tr": "tr",
    "english": "en", "ingilizce": "en", "en_us": "en", "en_gb": "en",
}


def normalize(code: str | None) -> str:
    """Map anything (``en``, ``en-US``, ``EN``, ``english``) to a supported code."""
    if not code:
        return DEFAULT_LANGUAGE
    value = str(code).strip().lower().replace("-", "_")
    for candidate in (value, value.split("_")[0], value.split(".")[0]):
        if candidate in SUPPORTED:
            return candidate
        if candidate in _ALIASES:
            return _ALIASES[candidate]
    return DEFAULT_LANGUAGE


def language_from_env() -> str:
    """Best-effort language from ``MAMIDLABS_LANG``/``LANG`` (installer fallback)."""
    for name in ("MAMIDLABS_LANG", "LANG", "LC_ALL", "LANGUAGE"):
        raw = os.environ.get(name)
        if not raw:
            continue
        code = normalize(raw)
        if code in SUPPORTED:
            return code
    return DEFAULT_LANGUAGE


def set_language(code: str | None) -> str:
    """Set the process-wide language and return the code actually in effect."""
    global _current
    _current = normalize(code)
    return _current


def current() -> str:
    return _current


def configure_console() -> None:
    """Make ``stdout``/``stderr`` able to carry non-ASCII text.

    macOS terminals are UTF-8, but when the output is **redirected** (a pipe, a
    file, the installer's log) the stream can fall back to an ASCII/locale codec
    and printing a Turkish character raises :class:`UnicodeEncodeError`.
    Reconfiguring the streams to UTF-8 (with ``replace`` as a last resort) keeps
    the CLI, ``doctor`` and the installer logs readable instead of crashing.
    """
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, OSError, ValueError):
            continue


def t(key: str, **fmt: object) -> str:
    """Translate ``key``; unknown keys fall back to Turkish, then to the key.

    ``fmt`` values are substituted with :meth:`str.format` so catalogs can use
    ``{name}`` placeholders.
    """
    text = _catalog(_current).get(key)
    if text is None:
        text = _catalog(DEFAULT_LANGUAGE).get(key)
    if text is None:
        return key
    if fmt:
        try:
            return text.format(**fmt)
        except (KeyError, IndexError, ValueError):
            return text
    return text


def has(key: str) -> bool:
    """True when the key exists in the current or the fallback catalog."""
    return key in _catalog(_current) or key in _catalog(DEFAULT_LANGUAGE)


def keys() -> set[str]:
    """Every key known to the current catalog (used by the parity test)."""
    return set(_catalog(_current))


__all__ = [
    "SUPPORTED", "DEFAULT_LANGUAGE", "LOCALES_DIR", "available", "normalize",
    "language_from_env", "set_language", "current", "configure_console", "t",
    "has", "keys",
]
