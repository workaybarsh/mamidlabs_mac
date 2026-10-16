"""The Qt6 setup wizard: a ``QWizard`` of 13 pages.

Page order mirrors the Windows (Inno Setup) wizard exactly:

    dil → karşılama → lisans → klasör → donanım raporu → profil →
    (kendi modellerin) → (API) → (bileşenler) → hazır → kurulum →
    özet → bitiş

The optional pages follow the profile choice: *own models* only for the "own"
choice, *API* only when not downloading models, *components* only when a local
profile is being installed — the same rule the Windows wizard uses.

The wizard only drives :mod:`mamidlabs.wizard` helpers and
``scripts/install-mamidlabs.sh``; it writes the user's choices into
``settings/api.json`` and shows the installer's progress file.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QTimer, QUrl, Qt
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (QCheckBox, QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPlainTextEdit, QProgressBar, QPushButton,
                               QRadioButton, QTextBrowser, QVBoxLayout, QWidget,
                               QWizard, QWizardPage)

from ..core import hwinfo, i18n
from ..core.paths import Paths
from ..core.settings import Settings
from . import (INSTALL_PROFILES, build_install_args, build_smoke_args, find_eula,
               find_install_script, parse_progress, repo_root, stage_names,
               step_label)

ID_LANG, ID_WELCOME, ID_LICENSE, ID_FOLDER, ID_REPORT, ID_PROFILE, ID_OWN, \
    ID_API, ID_COMPONENTS, ID_READY, ID_INSTALL, ID_SUMMARY, ID_FINISH = range(13)


class _Page(QWizardPage):
    """A page whose title/subtitle come from the i18n catalog."""

    def __init__(self, title_key: str, subtitle_key: str = "") -> None:
        super().__init__()
        self.title_key = title_key
        self.subtitle_key = subtitle_key

    def retranslate(self) -> None:  # overridden by subclasses that add widgets
        self.setTitle(i18n.t(self.title_key))
        if self.subtitle_key:
            self.setSubTitle(i18n.t(self.subtitle_key))


class LanguagePage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.lang.title", "wizard.lang.subtitle")
        layout = QVBoxLayout(self)
        self.label = QLabel()
        self.combo = QComboBox()
        self.combo.addItem("Türkçe", "tr")
        self.combo.addItem("English", "en")
        self.combo.setCurrentIndex(0 if i18n.current() == "tr" else 1)
        self.combo.currentIndexChanged.connect(
            lambda _i: self.wizard()._set_language(self.combo.currentData()))
        layout.addWidget(self.label)
        layout.addWidget(self.combo)
        layout.addStretch(1)

    def retranslate(self) -> None:
        super().retranslate()
        self.label.setText(i18n.t("wizard.lang.label"))


class WelcomePage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.welcome.title", "wizard.welcome.subtitle")
        layout = QVBoxLayout(self)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(self.body)

    def retranslate(self) -> None:
        super().retranslate()
        self.body.setText(i18n.t("wizard.welcome.body"))


class LicensePage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.license.title", "wizard.license.subtitle")
        layout = QVBoxLayout(self)
        self.view = QTextBrowser()
        path = find_eula()
        if path is not None:
            try:
                self.view.setPlainText(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                path = None
        self.accept = QCheckBox()
        self.accept.toggled.connect(self.completeChanged)
        self.missing = path is None
        layout.addWidget(self.view, 1)
        layout.addWidget(self.accept)

    def isComplete(self) -> bool:  # noqa: N802 - Qt API
        return self.accept.isChecked()

    def retranslate(self) -> None:
        super().retranslate()
        self.accept.setText(i18n.t("wizard.license.accept"))
        if self.missing:
            self.view.setPlainText(i18n.t("wizard.license.missing"))


class FolderPage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.folder.title", "wizard.folder.subtitle")
        layout = QVBoxLayout(self)
        self.label = QLabel()
        row = QHBoxLayout()
        self.edit = QLineEdit()
        self.browse = QPushButton()
        self.browse.clicked.connect(self._choose)
        row.addWidget(self.edit, 1)
        row.addWidget(self.browse)
        layout.addWidget(self.label)
        layout.addLayout(row)
        layout.addStretch(1)

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        if not self.edit.text():
            self.edit.setText(str(self.wizard().root_path))

    def _choose(self) -> None:
        chosen = QFileDialog.getExistingDirectory(self, i18n.t("wizard.folder.label"),
                                                  self.edit.text())
        if chosen:
            self.edit.setText(chosen)

    def root(self) -> Path:
        text = self.edit.text().strip()
        return Path(text) if text else self.wizard().root_path

    def retranslate(self) -> None:
        super().retranslate()
        self.label.setText(i18n.t("wizard.folder.label"))
        self.browse.setText(i18n.t("wizard.folder.browse"))


class ReportPage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.report.title", "wizard.report.subtitle")
        layout = QVBoxLayout(self)
        self.view = QTextBrowser()
        self.view.setOpenExternalLinks(False)
        layout.addWidget(self.view, 1)
        self.done = False

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        if self.done:
            return
        self.view.setPlainText(i18n.t("wizard.report.measuring"))
        self.wizard().repaint()
        try:
            report = hwinfo.measure(self.wizard().root())
        except Exception:  # noqa: BLE001 - a failed probe must not kill the wizard
            self.view.setPlainText(i18n.t("wizard.report.failed"))
            self.done = True
            return
        self.wizard().report = report
        self.view.setPlainText(self.wizard().format_report(report))
        self.done = True

    def retranslate(self) -> None:
        super().retranslate()
        report = getattr(self.wizard(), "report", None)
        if self.done and report is not None:
            self.view.setPlainText(self.wizard().format_report(report))


class ProfilePage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.profile.title", "wizard.profile.subtitle")
        layout = QVBoxLayout(self)
        self.body = QLabel()
        self.body.setWordWrap(True)
        layout.addWidget(self.body)
        self.buttons: dict[str, QRadioButton] = {}
        for choice in ("lite", "flash", "later", "own"):
            button = QRadioButton()
            self.buttons[choice] = button
            layout.addWidget(button)
        layout.addStretch(1)
        self.buttons["lite"].setChecked(True)

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        report = getattr(self.wizard(), "report", None)
        if report is not None:
            recommended = hwinfo.recommend(report)
            if recommended in self.buttons:
                self.buttons[recommended].setChecked(True)
            if recommended == "own":
                self.buttons["later"].setChecked(True)

    def choice(self) -> str:
        for choice, button in self.buttons.items():
            if button.isChecked():
                return choice
        return "lite"

    def retranslate(self) -> None:
        super().retranslate()
        self.body.setText(i18n.t("wizard.profile.body"))
        for choice, key in (("lite", "wizard.profile.lite"), ("flash", "wizard.profile.pro"),
                            ("later", "wizard.profile.later"), ("own", "wizard.profile.own")):
            self.buttons[choice].setText(i18n.t(key))


class OwnPage(_Page):
    KEYS = (("llm", "wizard.own.llm"), ("image", "wizard.own.image"),
            ("video", "wizard.own.video"))

    def __init__(self) -> None:
        super().__init__("wizard.own.title", "wizard.own.subtitle")
        layout = QVBoxLayout(self)
        self.body = QLabel()
        self.body.setWordWrap(True)
        layout.addWidget(self.body)
        self.labels: dict[str, QLabel] = {}
        self.edits: dict[str, QLineEdit] = {}
        self.browses: dict[str, QPushButton] = {}
        for name, key in self.KEYS:
            row = QHBoxLayout()
            label = QLabel()
            edit = QLineEdit()
            edit.textChanged.connect(self.completeChanged)
            browse = QPushButton()
            browse.clicked.connect(lambda _c=False, n=name: self._choose(n))
            row.addWidget(label)
            row.addWidget(edit, 1)
            row.addWidget(browse)
            layout.addLayout(row)
            self.labels[name] = label
            self.edits[name] = edit
            self.browses[name] = browse
        layout.addStretch(1)

    def _choose(self, name: str) -> None:
        path, _ = QFileDialog.getOpenFileName(self, self.labels[name].text())
        if path:
            self.edits[name].setText(path)

    def isComplete(self) -> bool:  # noqa: N802 - Qt API
        for edit in self.edits.values():
            value = edit.text().strip()
            if value and not Path(value).exists():
                return False
        return True

    def validatePage(self) -> bool:  # noqa: N802 - Qt API
        for edit in self.edits.values():
            value = edit.text().strip()
            if value and not Path(value).exists():
                from PySide6.QtWidgets import QMessageBox

                QMessageBox.warning(self, self.title(),
                                    i18n.t("wizard.own.not_found", path=value))
                return False
        return True

    def values(self) -> dict[str, str]:
        return {name: edit.text().strip() for name, edit in self.edits.items()}

    def retranslate(self) -> None:
        super().retranslate()
        self.body.setText(i18n.t("wizard.own.body"))
        for name, key in self.KEYS:
            self.labels[name].setText(i18n.t(key))
            self.browses[name].setText(i18n.t("wizard.own.browse"))

    def _cycle(self) -> None:  # pragma: no cover - helper kept for symmetry
        return None


class ApiPage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.api.title", "wizard.api.subtitle")
        layout = QVBoxLayout(self)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.open_box = QCheckBox()
        layout.addWidget(self.body)
        layout.addWidget(self.open_box)
        layout.addStretch(1)

    def retranslate(self) -> None:
        super().retranslate()
        self.body.setText(i18n.t("wizard.api.body"))
        self.open_box.setText(i18n.t("wizard.api.open"))


class ComponentsPage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.components.title", "wizard.components.subtitle")
        layout = QVBoxLayout(self)
        self.body = QLabel()
        self.body.setWordWrap(True)
        layout.addWidget(self.body)
        self.boxes: dict[str, QCheckBox] = {}
        for name in ("media", "audio", "ocr", "smoke"):
            box = QCheckBox()
            box.setChecked(True)
            layout.addWidget(box)
            self.boxes[name] = box
        layout.addStretch(1)

    def retranslate(self) -> None:
        super().retranslate()
        self.body.setText(i18n.t("wizard.components.body"))
        for name in ("media", "audio", "ocr", "smoke"):
            self.boxes[name].setText(i18n.t(f"wizard.components.{name}"))


class ReadyPage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.ready.title", "wizard.ready.subtitle")
        layout = QVBoxLayout(self)
        self.view = QTextBrowser()
        layout.addWidget(self.view, 1)

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        self.view.setPlainText(self.wizard().format_summary())

    def retranslate(self) -> None:
        super().retranslate()
        if self.wizard().currentId() == ID_READY:
            self.view.setPlainText(self.wizard().format_summary())


class InstallPage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.install.title", "wizard.install.subtitle")
        layout = QVBoxLayout(self)
        self.status = QLabel()
        self.bar = QProgressBar()
        self.bar.setRange(0, 0)  # busy until the progress file gives a total
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        layout.addWidget(self.status)
        layout.addWidget(self.bar)
        layout.addWidget(self.log, 1)
        self.finished = False
        self.process: subprocess.Popen | None = None
        self.timer = QTimer(self)
        self.timer.setInterval(400)
        self.timer.timeout.connect(self._poll)

    def isComplete(self) -> bool:  # noqa: N802 - Qt API
        return self.finished

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        self.finished = False
        self.bar.setRange(0, 0)
        self.log.clear()
        self.status.setText(i18n.t("wizard.install.starting"))
        try:
            self.wizard().start_install()
        except Exception as exc:  # noqa: BLE001 - present, do not crash
            self._fail(str(exc))
            return
        self.timer.start()

    def _fail(self, message: str) -> None:
        self.status.setText(message)
        self.log.appendPlainText(message)
        self.finished = True
        self.timer.stop()
        self.wizard().install_failed = True
        self.completeChanged.emit()

    def _poll(self) -> None:
        wiz = self.wizard()
        wiz.read_progress()
        index, total, step = wiz.progress
        if step:
            self.status.setText(i18n.t("wizard.install.step", name=step_label(step),
                                       index=index, total=total))
        if total:
            self.bar.setRange(0, total)
            self.bar.setValue(min(index, total))
        for line in wiz.drain_log():
            self.log.appendPlainText(line)
        if wiz.process is not None and wiz.process.poll() is not None:
            wiz.process = None
            if wiz.smoke_pending:
                wiz.start_smoke()
                return
            self.timer.stop()
            self.finished = True
            self.bar.setRange(0, total or 1)
            self.bar.setValue(total or 1)
            self.completeChanged.emit()
            self.wizard().next()

    def retranslate(self) -> None:
        super().retranslate()
        if not self.finished:
            self.status.setText(i18n.t("wizard.install.running"))


class SummaryPage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.summary.title", "wizard.summary.subtitle")
        layout = QVBoxLayout(self)
        self.view = QTextBrowser()
        layout.addWidget(self.view, 1)

    def initializePage(self) -> None:  # noqa: N802 - Qt API
        self.view.setPlainText(self.wizard().format_summary_file())

    def retranslate(self) -> None:
        super().retranslate()
        if self.wizard().currentId() == ID_SUMMARY:
            self.view.setPlainText(self.wizard().format_summary_file())


class FinishPage(_Page):
    def __init__(self) -> None:
        super().__init__("wizard.finish.title", "wizard.finish.subtitle")
        layout = QVBoxLayout(self)
        self.body = QLabel()
        self.body.setWordWrap(True)
        self.launch_box = QCheckBox()
        self.launch_box.setChecked(True)
        layout.addWidget(self.body)
        layout.addWidget(self.launch_box)
        layout.addStretch(1)

    def retranslate(self) -> None:
        super().retranslate()
        self.body.setText(i18n.t("wizard.finish.body"))
        self.launch_box.setText(i18n.t("wizard.finish.launch"))


class SetupWizard(QWizard):
    """The wizard the installer's ``.desktop``/``.app`` shortcut opens."""

    def __init__(self, root: Path | str | None = None,
                 language: str | None = None) -> None:
        super().__init__()
        i18n.configure_console()
        self.setWizardStyle(QWizard.WizardStyle.ModernStyle)
        self.setWindowTitle(i18n.t("wizard.title"))
        self.resize(860, 640)
        self.setOption(QWizard.WizardOption.NoBackButtonOnStartPage, True)

        self.root_path = Path(root) if root else Paths().root
        self.report: hwinfo.Report | None = None
        self.process: subprocess.Popen | None = None
        self.smoke_pending = False
        self.install_failed = False
        self.progress: tuple[int, int, str] = (0, 0, "")
        self._log_handle = None
        self._log_path: Path | None = None
        self._log_offset = 0

        settings_language = _settings_language(self.root_path)
        i18n.set_language(language or settings_language or i18n.language_from_env())

        self.pages = {
            ID_LANG: LanguagePage(),
            ID_WELCOME: WelcomePage(),
            ID_LICENSE: LicensePage(),
            ID_FOLDER: FolderPage(),
            ID_REPORT: ReportPage(),
            ID_PROFILE: ProfilePage(),
            ID_OWN: OwnPage(),
            ID_API: ApiPage(),
            ID_COMPONENTS: ComponentsPage(),
            ID_READY: ReadyPage(),
            ID_INSTALL: InstallPage(),
            ID_SUMMARY: SummaryPage(),
            ID_FINISH: FinishPage(),
        }
        for page_id, page in self.pages.items():
            self.setPage(page_id, page)
        self.setStartId(ID_LANG)
        self.currentIdChanged.connect(self._on_page_changed)
        self._retranslate()
        self.setButtonText(QWizard.WizardButton.FinishButton, i18n.t("wizard.button.finish"))
        self.setButtonText(QWizard.WizardButton.NextButton, i18n.t("wizard.button.next"))
        self.setButtonText(QWizard.WizardButton.BackButton, i18n.t("wizard.button.back"))
        self.setButtonText(QWizard.WizardButton.CancelButton, i18n.t("wizard.button.cancel"))

    # --- language ------------------------------------------------------------
    def _set_language(self, code: str) -> None:
        i18n.set_language(code)
        try:
            settings = _settings(self.root())
            settings["language"] = i18n.current()
            settings.save()
        except Exception:  # noqa: BLE001 - settings are written again at install
            pass
        self._retranslate()

    def _retranslate(self) -> None:
        self.setWindowTitle(i18n.t("wizard.title"))
        for page in self.pages.values():
            page.retranslate()

    # --- helpers -------------------------------------------------------------
    def root(self) -> Path:
        return self.pages[ID_FOLDER].root()

    def profile_choice(self) -> str:
        return self.pages[ID_PROFILE].choice()

    def install_profile(self) -> str | None:
        choice = self.profile_choice()
        return choice if choice in INSTALL_PROFILES else None

    def format_report(self, report: hwinfo.Report) -> str:
        lines = []
        if report.gpu_name:
            gpu = report.gpu_name
            if report.vram_mib:
                gpu += f" — {report.vram_mib} MiB"
            lines.append(f"{i18n.t('wizard.report.gpu')}: {gpu}")
        else:
            lines.append(f"{i18n.t('wizard.report.gpu')}: {i18n.t('wizard.report.no_gpu')}")
        if report.cpu:
            lines.append(f"{i18n.t('wizard.report.cpu')}: {report.cpu} ({report.cores})")
        if report.ram_mib:
            lines.append(f"{i18n.t('wizard.report.ram')}: {report.ram_mib / 1024:.1f} GB")
        if report.distro:
            lines.append(f"{i18n.t('wizard.report.os')}: {report.distro}")
        if report.free_gib:
            lines.append(f"{i18n.t('wizard.report.disk')}: {report.free_gib:.1f} GB")
        lines.append("")
        lines.append(f"{i18n.t('wizard.report.recommend')}: "
                     f"{i18n.t('wizard.profile.' + ('pro' if hwinfo.recommend(report) == 'flash' else hwinfo.recommend(report)))}")
        for key in hwinfo.warnings(report):
            lines.append(f"• {i18n.t(key)}")
        return "\n".join(lines)

    def format_summary(self) -> str:
        lines = [f"{i18n.t('wizard.folder.label')}: {self.root()}",
                 f"{i18n.t('wizard.profile.title')}: "
                 f"{i18n.t('wizard.profile.' + ('pro' if self.profile_choice() == 'flash' else self.profile_choice()))}"]
        if self.profile_choice() == "own":
            values = self.pages[ID_OWN].values()
            for name, key in (("llm", "wizard.own.llm"), ("image", "wizard.own.image"),
                              ("video", "wizard.own.video")):
                if values.get(name):
                    lines.append(f"{i18n.t(key)} {values[name]}")
        if self.pages[ID_API].open_box.isChecked():
            lines.append(f"• {i18n.t('wizard.api.open')}")
        if self.install_profile():
            boxes = self.pages[ID_COMPONENTS].boxes
            chosen = [i18n.t(f"wizard.components.{name}")
                      for name in ("media", "audio", "ocr") if boxes[name].isChecked()]
            lines.append(f"{i18n.t('wizard.components.title')}: " + ", ".join(chosen))
        lines.append("")
        if self.install_profile():
            lines.append(i18n.t("wizard.ready.download_hint"))
        else:
            lines.append(i18n.t("wizard.ready.no_download_hint"))
        lines.append(i18n.t("wizard.ready.intro"))
        return "\n".join(lines)

    def format_summary_file(self) -> str:
        path = self.root() / "logs" / "kurulum-ozeti.txt"
        if not path.is_file():
            return i18n.t("wizard.summary.missing", path=path)
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            return i18n.t("wizard.summary.missing", path=path)

    # --- page flow -----------------------------------------------------------
    def nextId(self) -> int:  # noqa: N802 - Qt API
        current = self.currentId()
        if current == ID_PROFILE:
            choice = self.profile_choice()
            if choice == "own":
                return ID_OWN
            if choice == "later":
                return ID_API
            return ID_COMPONENTS
        if current == ID_OWN:
            return ID_API
        if current == ID_API:
            return ID_COMPONENTS if self.install_profile() else ID_READY
        if current == ID_COMPONENTS:
            return ID_READY
        if current == ID_READY:
            return ID_INSTALL
        if current == ID_INSTALL:
            return ID_SUMMARY
        if current == ID_SUMMARY:
            return ID_FINISH
        return current + 1

    def _on_page_changed(self, page_id: int) -> None:
        back = self.button(QWizard.WizardButton.BackButton)
        cancel = self.button(QWizard.WizardButton.CancelButton)
        if back is not None:
            back.setEnabled(page_id not in (ID_INSTALL, ID_SUMMARY, ID_FINISH))
        if cancel is not None:
            cancel.setEnabled(page_id < ID_INSTALL)

    # --- settings ------------------------------------------------------------
    def write_settings(self) -> None:
        settings = _settings(self.root())
        settings["language"] = i18n.current()
        choice = self.profile_choice()
        if choice in INSTALL_PROFILES:
            settings["localProfile"] = choice
        if choice == "own":
            values = self.pages[ID_OWN].values()
            if values.get("llm"):
                settings["localModels"] = [values["llm"]]
            if values.get("image"):
                settings["imageLocalModel"] = values["image"]
            if values.get("video"):
                settings["videoLocalModel"] = values["video"]
        if self.pages[ID_API].open_box.isChecked():
            settings["firstRunApiSettings"] = True
        settings.save()

    # --- install -------------------------------------------------------------
    def _log_file(self) -> Path:
        logs = self.root() / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        return logs / "kurulum.log"

    def start_install(self) -> None:
        script = find_install_script()
        if script is None:
            raise FileNotFoundError(i18n.t("wizard.install.failed", path="scripts/install-mamidlabs.sh"))
        self.install_failed = False
        self.progress = (0, 0, "")
        self.write_settings()
        boxes = self.pages[ID_COMPONENTS].boxes
        args = build_install_args(
            self.root(), self.install_profile(), i18n.current(),
            download_models=self.install_profile() is not None,
            media=boxes["media"].isChecked(), audio=boxes["audio"].isChecked(),
            ocr=boxes["ocr"].isChecked(),
        )
        self.smoke_pending = boxes["smoke"].isChecked() and self.install_profile() is not None
        self._launch([str(script), *args])

    def start_smoke(self) -> None:
        script = script_for("smoke-test.sh")
        if script is None:
            self.smoke_pending = False
            return
        args = build_smoke_args(self.root(), self.install_profile())
        self._launch([str(script), *args])

    def _launch(self, argv: list[str]) -> None:
        path = self._log_file()
        self._log_path = path
        self._log_offset = path.stat().st_size if path.exists() else 0
        self._log_handle = open(path, "a", encoding="utf-8", errors="replace")
        env = dict(os.environ, MAMIDLABS_ROOT=str(self.root()),
                   MAMIDLABS_LANG=i18n.current(), PYTHONIOENCODING="utf-8")
        self.process = subprocess.Popen(  # noqa: S603 - fixed, in-tree script
            argv, stdout=self._log_handle, stderr=subprocess.STDOUT,
            cwd=str(repo_root()), env=env)

    def read_progress(self) -> None:
        path = self.root() / "logs" / "kurulum-adim.txt"
        try:
            self.progress = parse_progress(path.read_text(encoding="utf-8", errors="replace"))
        except OSError:
            self.progress = (0, 0, "")

    def drain_log(self) -> list[str]:
        if self._log_path is None:
            return []
        try:
            with open(self._log_path, encoding="utf-8", errors="replace") as handle:
                handle.seek(self._log_offset)
                chunk = handle.read()
                self._log_offset = handle.tell()
        except OSError:
            return []
        return [line for line in chunk.splitlines() if line.strip()]

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt API
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
        if self._log_handle is not None:
            self._log_handle.close()
            self._log_handle = None
        super().closeEvent(event)

    # --- finish --------------------------------------------------------------
    def accept(self) -> None:
        if self.pages[ID_FINISH].launch_box.isChecked():
            self.launch_app()
        super().accept()

    def launch_app(self) -> None:
        launcher = self.root() / "mamidlabs-launch"
        try:
            if launcher.is_file():
                subprocess.Popen([str(launcher)], cwd=str(self.root()),
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                 start_new_session=True)
            else:
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.root())))
        except OSError:
            pass


# --- small helpers -----------------------------------------------------------


def script_for(name: str):
    """Locate a sibling shell script next to ``install-mamidlabs.sh``."""
    install = find_install_script()
    if install is None:
        return None
    candidate = install.parent / name
    return candidate if candidate.is_file() else None


def _settings(root: Path) -> Settings:
    return Settings(Paths(root))


def _settings_language(root: Path) -> str | None:
    try:
        return _settings(root).language
    except Exception:  # noqa: BLE001 - never let settings break the wizard
        return None


def main(argv: list[str] | None = None) -> int:
    """Entry point used by ``python -m mamidlabs.wizard``."""
    from PySide6.QtWidgets import QApplication

    argv = list(sys.argv if argv is None else argv)
    root = _arg_value(argv, "--root")
    language = _arg_value(argv, "--lang")

    app = QApplication.instance() or QApplication([argv[0] if argv else "mamidlabs-setup"])
    app.setApplicationName(i18n.t("wizard.title"))
    wizard = SetupWizard(root=root, language=language)
    wizard.show()
    return app.exec()


def _arg_value(argv: list[str], name: str) -> str | None:
    if name in argv:
        index = argv.index(name)
        if index + 1 < len(argv):
            return argv[index + 1]
    return None
