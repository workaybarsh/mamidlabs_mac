"""Setup wizard — the pure helpers (no Qt required).

The window itself is exercised in ``test_wizard_gui.py`` so a host without Qt
still runs everything here.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from mamidlabs import wizard
from mamidlabs.core import i18n


def test_build_install_args_local_profile():
    args = wizard.build_install_args("/root", "lite", "tr")
    assert args == ["--root", "/root", "--language", "tr", "--profile", "lite"]


def test_build_install_args_skips_unchecked_components():
    args = wizard.build_install_args("/r", "flash", "en", media=False, audio=False,
                                     ocr=False)
    assert args[:6] == ["--root", "/r", "--language", "en", "--profile", "flash"]
    assert "--skip-media" in args and "--skip-audio" in args and "--skip-ocr" in args


def test_build_install_args_without_download_skips_models():
    args = wizard.build_install_args("/r", None, "tr", download_models=False)
    assert "--skip-models" in args
    assert "--profile" not in args


def test_build_install_args_still_skips_models_when_profile_is_none():
    args = wizard.build_install_args("/r", None, "en")
    assert "--skip-models" in args and "--profile" not in args


def test_build_smoke_args():
    assert wizard.build_smoke_args("/r", "lite") == ["--root", "/r", "--profile", "lite"]
    assert wizard.build_smoke_args("/r", None) == ["--root", "/r"]


@pytest.mark.parametrize("text,expected", [
    ("1\n7\nlayout\n", (1, 7, "layout")),
    ("2\n7\nllama\n", (2, 7, "llama")),
    ("", (0, 0, "")),
    ("x\ny\nz\n", (0, 0, "")),
    ("3\n7\n", (0, 0, "")),
    ("0\n0\npreflight\n", (0, 0, "")),
])
def test_parse_progress(text, expected):
    assert wizard.parse_progress(text) == expected


def test_stage_names_track_the_installer_script():
    script = wizard.repo_root() / "scripts" / "install-mamidlabs.sh"
    text = script.read_text(encoding="utf-8")
    stages = wizard.stage_names()
    for stage in stages:
        assert f"stage_{stage}()" in text, f"{stage} aşaması betikte yok"
    assert "for stage in " + " ".join(stages) in text


def test_step_label_translates_and_falls_back():
    i18n.set_language("tr")
    assert wizard.step_label("llama") == "llama.cpp"
    assert wizard.step_label("verify") == "Doğrulama"
    assert wizard.step_label("bilinmeyen-adim") == "bilinmeyen-adim"


def test_find_install_script_honours_the_env_override(tmp_path, monkeypatch):
    fake = tmp_path / "install-mamidlabs.sh"
    fake.write_text("#!/usr/bin/env bash\n", encoding="utf-8")
    monkeypatch.setenv("MAMIDLABS_INSTALL_SCRIPT", str(fake))
    assert wizard.find_install_script() == fake


def test_find_install_script_finds_the_repo_copy(monkeypatch):
    monkeypatch.delenv("MAMIDLABS_INSTALL_SCRIPT", raising=False)
    found = wizard.find_install_script()
    assert found is not None
    assert found.name == "install-mamidlabs.sh"


def test_find_eula_exists_in_the_repo():
    assert wizard.find_eula() is not None


def test_every_wizard_key_used_in_code_is_in_the_catalogs():
    package = pathlib.Path(wizard.__file__).parent
    catalogs = {code: _catalog(code) for code in i18n.SUPPORTED}
    literal = re.compile(r"""["'](wizard\.[a-z_]+(?:\.[a-z_]+)*)["']""")
    for name in ("__init__.py", "setup.py", "__main__.py"):
        text = (package / name).read_text(encoding="utf-8")
        for key in literal.findall(text):
            for code, catalog in catalogs.items():
                assert _known(key, catalog), f"{code}.json eksik: {key}"
    # The dynamic families the window builds from lists.
    for code, catalog in catalogs.items():
        for stage in wizard.stage_names():
            assert f"wizard.stage.{stage}" in catalog, f"{code}: wizard.stage.{stage}"
        for comp in ("media", "audio", "ocr", "smoke"):
            assert f"wizard.components.{comp}" in catalog
        for profile in ("lite", "pro", "later", "own"):
            assert f"wizard.profile.{profile}" in catalog


def _catalog(code: str) -> dict[str, str]:
    return json.loads((i18n.LOCALES_DIR / f"{code}.json").read_text(encoding="utf-8"))


def _known(key: str, catalog: dict[str, str]) -> bool:
    return key in catalog or any(existing.startswith(key + ".") for existing in catalog)
