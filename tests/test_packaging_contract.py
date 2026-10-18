"""Packaging contract: version, the .dmg build, the wizard launchers and locales."""

from __future__ import annotations

import pathlib
import re

import pytest

from mamidlabs import __version__
from mamidlabs.core import i18n

REPO = pathlib.Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
PKG = REPO / "packaging" / "macos"


def test_version_is_consistent():
    """``__init__`` and ``pyproject.toml`` must agree (release tag derives from it)."""
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert f'version = "{__version__}"' in pyproject


def test_locale_catalogs_ship_with_the_package():
    for code in i18n.SUPPORTED:
        assert (i18n.LOCALES_DIR / f"{code}.json").is_file()
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert '"mamidlabs" = ["locales/*.json"]' in pyproject, \
        "dil katalogları paket verisine eklenmeli"


def test_dmg_build_script_exists_and_is_wired():
    script = PKG / "build-dmg.sh"
    assert script.is_file()
    text = script.read_text(encoding="utf-8")
    assert "hdiutil" in text
    assert "-format UDZO" in text
    assert "MamidLabs Kurulum" in text
    # The DMG must ship the wizard sources, not only the app.
    assert "mamidlabs-src" in text
    assert "MacOS-MamidLabsSetup" in text


def test_wizard_app_template_files_exist():
    assert (PKG / "Info.plist").is_file()
    assert (PKG / "MacOS-MamidLabsSetup").is_file()
    plist = (PKG / "Info.plist").read_text(encoding="utf-8")
    assert "@VERSION@" in plist
    assert "com.workaybarsh.mamidlabs.setup" in plist
    assert "MamidLabsSetup" in plist
    launcher = (PKG / "MacOS-MamidLabsSetup").read_text(encoding="utf-8")
    assert "-m mamidlabs.wizard" in launcher
    assert launcher.startswith("#!/bin/zsh")


def test_app_bundle_templates_are_still_placeholder_based():
    plist = (REPO / "packaging" / "Info.plist").read_text(encoding="utf-8")
    assert "@VERSION@" in plist
    launcher = (REPO / "packaging" / "MacOS-MamidLabs").read_text(encoding="utf-8")
    assert "@ROOT@" in launcher


def test_wizard_launcher_script_exists():
    launcher = SCRIPTS / "mamidlabs-setup.sh"
    assert launcher.is_file()
    text = launcher.read_text(encoding="utf-8")
    assert "-m mamidlabs.wizard" in text
    assert text.startswith("#!/bin/bash")
    # macOS ships bash 3.2: no associative arrays, mapfile or ${var,,}.
    for forbidden in ("declare -A", "mapfile", "local -n"):
        assert forbidden not in text, f"bash 4+ özelliği: {forbidden}"


def test_shell_scripts_use_lf_and_are_bash():
    for name in ("install-mamidlabs.sh", "manage-mamidlabs.sh",
                 "uninstall-mamidlabs.sh", "smoke-test.sh", "mamidlabs-setup.sh"):
        raw = (SCRIPTS / name).read_bytes()
        assert b"\r\n" not in raw, f"{name} LF satır sonu kullanmalı"
        assert raw.startswith(b"#!"), f"{name} shebang eksik"
        assert b"bash" in raw.split(b"\n", 1)[0], f"{name} bash shebang kullanmalı"


def test_installer_accepts_language_and_writes_progress():
    text = (SCRIPTS / "install-mamidlabs.sh").read_text(encoding="utf-8")
    assert "--language" in text
    assert re.search(r"case \"\$2\" in\s+tr\|en", text), "dil tr|en ile sınırlanmalı"
    assert "kurulum-adim.txt" in text, "sihirbaz ilerleme dosyası yazılmalı"
    assert "kurulum-ozeti.txt" in text, "sihirbaz özet dosyası yazılmalı"
    assert "MAMIDLABS_ROOT" in text


def test_wizard_registers_a_console_script():
    pyproject = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert 'mamidlabs-setup = "mamidlabs.wizard.__main__:main"' in pyproject


def test_pinned_versions_are_present():
    text = (SCRIPTS / "install-mamidlabs.sh").read_text(encoding="utf-8")
    for pinned in ("b10998", "b0f4b7b", "6ea2651", "86f886d"):
        assert pinned in text, f"sabit sürüm eksik: {pinned}"


@pytest.mark.parametrize("name", ["install-mamidlabs.sh", "uninstall-mamidlabs.sh"])
def test_uninstaller_never_touches_outside_the_root(name):
    text = (SCRIPTS / name).read_text(encoding="utf-8")
    assert "MAMIDLABS_ROOT" in text


def test_no_linux_only_assets_remain():
    """The .deb/desktop assets belong to the Linux repo, not this one."""
    assert not (REPO / "packaging" / "linux").exists()


def test_licence_matches_windows_parity_polyform_strict():
    """Lisans Windows sürümüyle aynı olmalı: PolyForm Strict 1.0.0 (tir. ticari)."""
    licence = (REPO / "LICENSE").read_bytes()
    assert not licence.startswith(b"\xef\xbb\xbf"), "LICENSE BOM'suz (LF) olmalı"
    assert licence.startswith(b"PolyForm Strict License 1.0.0"), \
        "LICENSE resmî PolyForm Strict 1.0.0 başlığıyla başlamalı"
    assert b"Noncommercial Purposes" in licence
    assert b"distributing the software or making changes or new works" in licence


def test_eula_ships_as_utf8_bom():
    """EULA.txt Windows sürümüyle aynı olmalı: UTF-8 BOM'lu PolyForm bildirimi."""
    eula = (REPO / "EULA.txt").read_bytes()
    assert eula.startswith(b"\xef\xbb\xbf"), "EULA.txt UTF-8 BOM taşımalı"
    assert "PolyForm Strict 1.0.0" in eula.decode("utf-8-sig")
