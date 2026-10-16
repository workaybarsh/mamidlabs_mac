"""Runtime localisation: catalog parity and the console-encoding guard."""

from __future__ import annotations

import io
import json
import sys

import pytest

from mamidlabs.core import i18n


def _catalog(code: str) -> dict[str, str]:
    return json.loads((i18n.LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8"))


def test_catalogs_have_identical_keys():
    tr, en = _catalog("tr"), _catalog("en")
    assert set(tr) == set(en), "TR ve EN aynı anahtar kümesine sahip olmalı"
    assert "prompt.system" in tr
    assert "wizard.title" in tr


def test_catalogs_are_not_empty():
    for code in i18n.SUPPORTED:
        assert len(_catalog(code)) > 100


@pytest.mark.parametrize("value,expected", [
    ("en", "en"), ("EN", "en"), ("en-US", "en"), ("english", "en"),
    ("tr", "tr"), ("tr_TR", "tr"), ("türkçe", "tr"), ("turkce", "tr"),
    ("klingon", "tr"), (None, "tr"), ("", "tr"),
])
def test_normalize_maps_aliases_to_supported_codes(value, expected):
    assert i18n.normalize(value) == expected


def test_language_setter_and_current():
    assert i18n.set_language("en") == "en"
    assert i18n.current() == "en"
    assert i18n.set_language("bilinmeyen") == "tr"


def test_unknown_key_returns_the_key_itself():
    assert i18n.t("bu.anahtar.yok") == "bu.anahtar.yok"


def test_translation_formatting_uses_placeholders():
    i18n.set_language("en")
    assert i18n.t("wizard.install.step", name="llama.cpp", index=2, total=7) == \
        "llama.cpp (2/7)"


def test_missing_english_key_falls_back_to_turkish():
    """A key that only exists in TR still renders (never an empty label)."""
    i18n._catalogs["en"] = {}  # simulate a truncated en.json
    try:
        assert i18n.t("wizard.title") == _catalog("tr")["wizard.title"]
    finally:
        i18n._catalogs.pop("en", None)


def test_configure_console_makes_turkish_printable():
    """Redirected output can fall back to ASCII (LANG=C); the CLI must fix it."""
    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="ascii")
    saved = sys.stdout
    sys.stdout = stream
    try:
        i18n.configure_console()
        print("şğıİı öçŞĞÜ")  # raises UnicodeEncodeError without the fix
        stream.flush()
        data = buffer.getvalue()
    finally:
        sys.stdout = saved
        stream.detach()
    assert "şğıİı" in data.decode("utf-8")
