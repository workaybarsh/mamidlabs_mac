"""Setup wizard — the Qt window (skipped without a usable Qt).

PySide6 can be installed while the system Qt libraries are missing, so the import
is guarded: the module skips instead of failing the whole run.
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from mamidlabs.core import i18n  # noqa: E402

pytest.importorskip("PySide6", reason="PySide6 is only needed for the window tests")

try:  # pragma: no cover - the guard is what matters
    from PySide6.QtWidgets import QApplication

    from mamidlabs.core.paths import Paths
    from mamidlabs.core.settings import Settings
    from mamidlabs.wizard.setup import (ID_API, ID_COMPONENTS, ID_INSTALL, ID_LANG,
                                        ID_OWN, ID_PROFILE, ID_READY, SetupWizard)
except ImportError as exc:  # pragma: no cover - missing system Qt libraries
    pytest.skip(f"Qt yüklenemedi: {exc}", allow_module_level=True)


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


def _wizard(tmp_path) -> SetupWizard:
    window = SetupWizard(root=tmp_path / "root", language="tr")
    window.restart()  # QWizard only tracks currentId() once it is started
    return window


def test_wizard_builds_all_pages(qapp, tmp_path):
    window = _wizard(tmp_path)
    try:
        assert window.windowTitle() == i18n.t("wizard.title")
        assert len(window.pages) == 13
        assert window.pages[ID_LANG].title() == i18n.t("wizard.lang.title")
    finally:
        window.close()


def test_language_switch_retranslates_live(qapp, tmp_path):
    window = _wizard(tmp_path)
    try:
        turkish = window.pages[ID_LANG].title()
        window._set_language("en")
        assert window.windowTitle() == "MamidLabs setup wizard"
        assert window.pages[ID_LANG].title() == "Language"
        window._set_language("tr")
        assert window.pages[ID_LANG].title() == turkish
    finally:
        window.close()


def test_language_switch_is_persisted(qapp, tmp_path):
    window = _wizard(tmp_path)
    try:
        window._set_language("en")
        saved = Settings(Paths(window.root()))
        saved.load()
        assert saved.language == "en"
    finally:
        window.close()


def test_profile_page_prefills_the_recommendation(qapp, tmp_path):
    """macOS önerisi birleşik belleğe ve Apple Silicon'a bakar."""
    from mamidlabs.core import hwinfo

    window = _wizard(tmp_path)
    try:
        window.report = hwinfo.Report(ram_mib=36 * 1024, apple_silicon=True)
        window.pages[ID_PROFILE].initializePage()
        assert window.pages[ID_PROFILE].choice() == "flash"

        window.report = hwinfo.Report(ram_mib=16 * 1024, apple_silicon=True)
        window.pages[ID_PROFILE].initializePage()
        assert window.pages[ID_PROFILE].choice() == "lite"

        window.report = hwinfo.Report(ram_mib=64 * 1024, apple_silicon=False)
        window.pages[ID_PROFILE].initializePage()
        assert window.pages[ID_PROFILE].choice() == "later"
        assert window.install_profile() is None
    finally:
        window.close()


def test_report_page_formats_the_measurement(qapp, tmp_path):
    from mamidlabs.core import hwinfo

    window = _wizard(tmp_path)
    try:
        window.report = hwinfo.Report(gpus=[hwinfo.Gpu("Apple M3 Pro")],
                                      ram_mib=36 * 1024, cpu="Apple M3 Pro", cores=12,
                                      distro="macOS 15.1", free_gib=300.0,
                                      apple_silicon=True)
        text = window.format_report(window.report)
        assert "Apple M3 Pro" in text
        assert i18n.t("wizard.report.recommend") in text
    finally:
        window.close()


def test_page_flow_depends_on_the_profile_choice(qapp, tmp_path):
    window = _wizard(tmp_path)
    try:
        window.setCurrentId(ID_PROFILE)
        for choice, expected in (("own", ID_OWN), ("later", ID_API),
                                 ("lite", ID_COMPONENTS), ("flash", ID_COMPONENTS)):
            window.pages[ID_PROFILE].buttons[choice].setChecked(True)
            assert window.nextId() == expected, choice
        window.setCurrentId(ID_API)
        window.pages[ID_PROFILE].buttons["later"].setChecked(True)
        assert window.nextId() == ID_READY
        window.pages[ID_PROFILE].buttons["lite"].setChecked(True)
        assert window.nextId() == ID_COMPONENTS
    finally:
        window.close()


def test_install_page_reads_a_progress_file(qapp, tmp_path):
    window = _wizard(tmp_path)
    try:
        logs = window.root() / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "kurulum-adim.txt").write_text("3\n7\npython\n", encoding="utf-8")
        window.read_progress()
        assert window.progress == (3, 7, "python")
        (logs / "kurulum-adim.txt").write_text("cevap\n", encoding="utf-8")
        window.read_progress()
        assert window.progress == (0, 0, "")
    finally:
        window.close()


def test_summary_page_handles_a_missing_file(qapp, tmp_path):
    window = _wizard(tmp_path)
    try:
        expected = i18n.t("wizard.summary.missing",
                          path=window.root() / "logs" / "kurulum-ozeti.txt")
        assert window.format_summary_file() == expected
    finally:
        window.close()


def test_write_settings_records_the_choices(qapp, tmp_path):
    window = _wizard(tmp_path)
    try:
        window.pages[ID_PROFILE].buttons["own"].setChecked(True)
        window.pages[ID_OWN].edits["llm"].setText("/models/x.gguf")
        window.pages[ID_API].open_box.setChecked(True)
        window.write_settings()

        saved = Settings(Paths(window.root()))
        saved.load()
        assert saved["language"] == "tr"
        assert saved["localModels"] == ["/models/x.gguf"]
        assert saved["firstRunApiSettings"] is True
    finally:
        window.close()


def test_install_page_is_not_complete_until_finished(qapp, tmp_path):
    window = _wizard(tmp_path)
    try:
        page = window.pages[ID_INSTALL]
        assert page.isComplete() is False
        page.finished = True
        assert page.isComplete() is True
    finally:
        window.close()


def test_own_page_rejects_a_missing_file(qapp, tmp_path):
    window = _wizard(tmp_path)
    try:
        page = window.pages[ID_OWN]
        assert page.isComplete()  # empty fields are fine
        page.edits["llm"].setText(str(tmp_path / "yok.gguf"))
        assert not page.isComplete()
    finally:
        window.close()
