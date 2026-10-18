"""Main window: chat, profile/provider selection, chips and the turn worker."""

from __future__ import annotations

import html
import json
import threading

from PySide6.QtCore import QThread, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPlainTextEdit, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..core import i18n, providers
from ..core.inference import InferenceEngine
from ..core.manage import ModelManager
from ..core.paths import Paths
from ..core.profiles import PROFILE_IDS, catalog_for_display
from ..core.runner import WorkerRunner
from ..core.settings import Settings
from ..core.tools import MediaBridge, ToolRegistry
from .settings_dialog import ApiSettingsDialog
from .theme import STYLESHEET


class TurnWorker(QThread):
    event = Signal(dict)
    approval_needed = Signal(str, dict, str)

    def __init__(self, engine: InferenceEngine, history: list[dict], **kwargs) -> None:
        super().__init__()
        self.engine = engine
        self.history = history
        self.kwargs = kwargs
        self._approval_result: bool | None = None
        self._approval_lock = threading.Event()
        self._cancelled = threading.Event()

    def resolve_approval(self, allowed: bool) -> None:
        self._approval_result = allowed
        self._approval_lock.set()

    def cancel(self) -> None:
        self._cancelled.set()

    def _approve(self, name: str, arguments: dict, reason: str = "") -> bool:
        self._approval_result = None
        self._approval_lock.clear()
        self.approval_needed.emit(name, arguments, reason)
        # Wait up to 10 minutes; default to deny on timeout (as on Windows).
        self._approval_lock.wait(600)
        return bool(self._approval_result)

    def run(self) -> None:  # noqa: D401 - QThread entry point
        try:
            for event in self.engine.run_turn(self.history, approve=self._approve, **self.kwargs):
                if self._cancelled.is_set():
                    self.event.emit({"kind": "cancelled"})
                    break
                self.event.emit(event)
        except Exception as exc:  # noqa: BLE001 - surfaced in the chat
            self.event.emit({"kind": "error", "text": f"{type(exc).__name__}: {exc}"})


class ManageWorker(QThread):
    message = Signal(str)
    failed = Signal(str)

    def __init__(self, manager: ModelManager, action: str, profile: str) -> None:
        super().__init__()
        self.manager = manager
        self.action = action
        self.profile = profile

    def run(self) -> None:
        try:
            if self.action == "start":
                self.message.emit(self.manager.start(self.profile))
            elif self.action == "stop":
                self.message.emit(self.manager.stop())
            elif self.action == "closecomfy":
                self.message.emit(self.manager.close_comfy())
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self, paths: Paths, settings: Settings) -> None:
        super().__init__()
        self.paths = paths
        self.settings = settings
        self.paths.ensure_dirs()
        self.history: list[dict] = []
        self.worker: TurnWorker | None = None
        self.manage_worker: ManageWorker | None = None
        self.manager = ModelManager(paths, settings)
        runner = WorkerRunner(paths, settings)
        self.registry = ToolRegistry(paths, settings, runner,
                                     media=MediaBridge())  # media wired when configured
        self.engine = InferenceEngine(paths, settings, self.registry)

        self.setWindowTitle(i18n.t("app.name"))
        self.resize(980, 720)
        self.setStyleSheet(STYLESHEET)
        self._build_menu()
        self._build_layout()
        self._install_shortcut()
        self._retranslate()
        self._refresh_models()

    # --- layout --------------------------------------------------------------
    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu(i18n.t("app.name"))
        self.api_action = QAction(self)
        self.api_action.triggered.connect(self._open_api_settings)
        menu.addAction(self.api_action)

        self.language_menu = menu.addMenu("")
        self.language_group = QActionGroup(self)
        self.language_group.setExclusive(True)
        self.language_actions: dict[str, QAction] = {}
        for code in i18n.SUPPORTED:
            action = QAction(self)
            action.setCheckable(True)
            action.setChecked(code == i18n.current())
            action.triggered.connect(lambda _checked=False, c=code: self._set_language(c))
            self.language_group.addAction(action)
            self.language_menu.addAction(action)
            self.language_actions[code] = action

        # Profiller menüsü: MAX/FLASH'ta çaba istek başına seçilsin (model
        # yeniden yüklenmesin). Kapatılırsa sunucunun profil değeri kullanılır.
        self.profiles_menu = menu.addMenu("")
        self.auto_effort_action = QAction(self)
        self.auto_effort_action.setCheckable(True)
        self.auto_effort_action.setChecked(bool(self.settings.get("autoEffort", True)))
        self.auto_effort_action.toggled.connect(self._on_auto_effort_toggled)
        self.profiles_menu.addAction(self.auto_effort_action)

        self.quit_action = QAction(self)
        self.quit_action.triggered.connect(self.close)
        menu.addAction(self.quit_action)

    def _build_layout(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        top = QHBoxLayout()
        self.profile_label = QLabel()
        self.profile_box = QComboBox()
        self.profile_box.addItems([p.label for p in catalog_for_display()])
        self.profile_box.currentIndexChanged.connect(self._on_profile_changed)
        self.provider_label = QLabel()
        self.provider_box = QComboBox()
        self.provider_box.addItems(["local", *providers.provider_ids()])
        self.provider_box.currentTextChanged.connect(lambda _v: self._refresh_models())
        self.model_label = QLabel()
        self.model_box = QComboBox()
        self.start_button = QPushButton()
        self.start_button.clicked.connect(self._start_model)
        self.stop_button = QPushButton()
        self.stop_button.clicked.connect(lambda: self._manage("stop"))
        for widget in (self.profile_label, self.profile_box, self.provider_label,
                       self.provider_box, self.model_label, self.model_box,
                       self.start_button, self.stop_button):
            top.addWidget(widget)
        top.addStretch(1)
        layout.addLayout(top)

        self.chat = QTextBrowser()
        self.chat.setObjectName("chat")
        layout.addWidget(self.chat, 1)

        chips = QHBoxLayout()
        self.internet_chip = QCheckBox()
        self.agent_chip = QCheckBox()
        self.access_chip = QCheckBox()
        # Çip durumu ayarlardan gelir. "Tam erişim" varsayılanı KAPALI'dır:
        # yazma/çalıştırma araçları kullanıcı onayı ister (güvenli varsayılan).
        prefs = self.settings.get("uiPreferences") or {}
        self.internet_chip.setChecked(bool(prefs.get("internet", True)))
        self.agent_chip.setChecked(bool(prefs.get("agent", True)))
        self.access_chip.setChecked(bool(prefs.get("accessMode", False)))
        for chip in (self.internet_chip, self.agent_chip, self.access_chip):
            chip.toggled.connect(self._save_chips)
            chips.addWidget(chip)
        chips.addStretch(1)
        layout.addLayout(chips)

        bottom = QHBoxLayout()
        self.input = QPlainTextEdit()
        self.input.setObjectName("input")
        self.input.setFixedHeight(90)
        bottom.addWidget(self.input, 1)
        self.send_button = QPushButton()
        self.send_button.clicked.connect(self._send)
        self.stop_turn_button = QPushButton()
        self.stop_turn_button.setObjectName("stop")
        self.stop_turn_button.clicked.connect(self._cancel_turn)
        self.stop_turn_button.setEnabled(False)
        bottom.addWidget(self.send_button)
        bottom.addWidget(self.stop_turn_button)
        layout.addLayout(bottom)

        self.setCentralWidget(central)

    def _install_shortcut(self) -> None:
        """⌘+Enter sends on macOS; Ctrl+Enter works too (and elsewhere)."""
        for sequence in ("Ctrl+Return", "Meta+Return"):
            shortcut = QShortcut(QKeySequence(sequence), self.input)
            shortcut.activated.connect(self._send)

    def _retranslate(self) -> None:
        """(Re)apply every visible string in the current language."""
        self.api_action.setText(i18n.t("ui.menu.api"))
        self.quit_action.setText(i18n.t("ui.menu.quit"))
        self.language_menu.setTitle(i18n.t("ui.menu.language"))
        self.language_actions["tr"].setText("Türkçe")
        self.language_actions["en"].setText("English")
        self.profiles_menu.setTitle(i18n.t("ui.menu.profiles"))
        self.auto_effort_action.setText(i18n.t("ui.menu.auto_effort"))
        self.profile_label.setText(i18n.t("ui.label.profile"))
        self.provider_label.setText(i18n.t("ui.label.provider"))
        self.model_label.setText(i18n.t("ui.label.model"))
        self.start_button.setText(i18n.t("ui.button.start_model"))
        self.stop_button.setText(i18n.t("ui.button.stop_model"))
        self.internet_chip.setText(i18n.t("ui.chip.internet"))
        self.agent_chip.setText(i18n.t("ui.chip.agent"))
        self.access_chip.setText(i18n.t("ui.chip.access"))
        self.input.setPlaceholderText(i18n.t("ui.input.placeholder"))
        self.send_button.setText(i18n.t("ui.button.send"))
        self.stop_turn_button.setText(i18n.t("ui.button.stop"))
        self.statusBar().showMessage(i18n.t("ui.status.ready"))
        self.setWindowTitle(i18n.t("app.name"))

    def _set_language(self, code: str) -> None:
        i18n.set_language(code)
        self.settings.language = code
        self.settings.save()
        self._retranslate()
        self._refresh_models()

    # --- helpers -------------------------------------------------------------
    def _on_profile_changed(self, _index: int) -> None:
        profile = PROFILE_IDS[self.profile_box.currentIndex()] \
            if self.profile_box.currentIndex() < len(PROFILE_IDS) else "max"
        self.settings.local_profile = profile
        self.settings.save()

    def _on_auto_effort_toggled(self, checked: bool) -> None:
        self.settings["autoEffort"] = bool(checked)
        self.settings.save()

    def _save_chips(self, _checked: bool = False) -> None:
        """Persist the intent/access chips (access is off by default)."""
        self.settings["uiPreferences"] = {
            "internet": self.internet_chip.isChecked(),
            "agent": self.agent_chip.isChecked(),
            "accessMode": self.access_chip.isChecked(),
        }
        self.settings.save()

    def _current_profile(self) -> str:
        return self.settings.local_profile

    def _refresh_models(self) -> None:
        self.model_box.clear()
        provider_id = self.provider_box.currentText()
        if provider_id == "local":
            self.model_box.addItem(i18n.t("ui.model.local", profile=self._current_profile()))
        else:
            saved = self.settings.provider(provider_id)
            self.model_box.addItem(str(saved.get("model") or i18n.t("ui.model.choose")))

    def _append(self, role: str, text: str) -> None:
        colour = {"user": "#8ab4f8", "assistant": "#e6e6e6", "tool": "#9aa0aa",
                  "error": "#ff8a80", "status": "#9aa0aa"}.get(role, "#e6e6e6")
        label = i18n.t(f"ui.role.{role}") if i18n.has(f"ui.role.{role}") else role
        safe = html.escape(text).replace("\n", "<br>")
        self.chat.append(f'<div style="color:{colour}"><b>{label}:</b> {safe}</div>')

    # --- model management ----------------------------------------------------
    def _manage(self, action: str) -> None:
        if self.manage_worker and self.manage_worker.isRunning():
            return
        self.statusBar().showMessage(i18n.t("ui.status.model_action", action=action))
        self.manage_worker = ManageWorker(self.manager, action, self._current_profile())
        self.manage_worker.message.connect(self.statusBar().showMessage)
        self.manage_worker.failed.connect(self._on_manage_failed)
        self.manage_worker.start()

    def _start_model(self) -> None:
        self._manage("start")

    def _on_manage_failed(self, text: str) -> None:
        self.statusBar().showMessage(i18n.t("ui.model_failed.body"))
        QMessageBox.warning(self, i18n.t("ui.model_failed.title"), text)

    # --- chat ----------------------------------------------------------------
    def _send(self) -> None:
        text = self.input.toPlainText().strip()
        if not text or (self.worker and self.worker.isRunning()):
            return
        self.input.clear()
        self._append("user", text)
        self.history.append({"role": "user", "content": text})
        self._run_turn()

    def _run_turn(self) -> None:
        provider_id = self.provider_box.currentText()
        model = self.settings.provider(provider_id).get("model", "") if provider_id != "local" else ""
        chips = {"internet": self.internet_chip.isChecked(),
                 "agent": self.agent_chip.isChecked(),
                 "accessMode": self.access_chip.isChecked()}
        self.worker = TurnWorker(
            self.engine, self.history, chips=chips, provider=provider_id, model=str(model),
            profile=self._current_profile(),
            has_documents=any(m.get("role") == "user" and isinstance(m.get("content"), list)
                              for m in self.history),
        )
        self.worker.event.connect(self._on_event)
        self.worker.approval_needed.connect(self._on_approval)
        self.worker.finished.connect(self._on_turn_finished)
        self.send_button.setEnabled(False)
        self.stop_turn_button.setEnabled(True)
        self.statusBar().showMessage(i18n.t("ui.status.generating"))
        self.worker.start()

    def _cancel_turn(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.statusBar().showMessage(i18n.t("ui.status.stopped"))

    def _on_event(self, event: dict) -> None:
        kind = event.get("kind")
        if kind == "answer":
            self._append_streaming(event.get("text", ""))
        elif kind == "thinking":
            self.statusBar().showMessage(i18n.t("ui.status.thinking"))
        elif kind == "tool":
            self._append("tool", i18n.t("ui.tool", tool=event.get("tool")))
        elif kind == "denied":
            self._append("status", i18n.t("ui.status.denied"))
        elif kind == "error":
            self._append("error", event.get("text", ""))
        elif kind == "done":
            self._append("assistant", event.get("text", ""))
            data = event.get("data") or []
            if data:
                self.history.extend(data)

    def _append_streaming(self, text: str) -> None:
        self.chat.moveCursor(self.chat.textCursor().End)
        self.chat.insertPlainText(text)

    def _on_turn_finished(self) -> None:
        self.send_button.setEnabled(True)
        self.stop_turn_button.setEnabled(False)
        self.statusBar().showMessage(i18n.t("ui.status.ready"))

    def _on_approval(self, name: str, arguments: dict, reason: str = "") -> None:
        preview = json.dumps(arguments, ensure_ascii=False, indent=2)[:1200]
        body = i18n.t("ui.approval.question", name=html.escape(name),
                      preview=html.escape(preview))
        if reason:
            # Untrusted content was read this turn: tell the user why we ask
            # even though the "full access" chip may be on.
            body += "<br><br><i>" + html.escape(reason) + "</i>"
        answer = QMessageBox.question(
            self, i18n.t("ui.approval.title"), body,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if self.worker:
            self.worker.resolve_approval(answer == QMessageBox.StandardButton.Yes)

    # --- settings ------------------------------------------------------------
    def _open_api_settings(self) -> None:
        dialog = ApiSettingsDialog(self.settings, self)
        if dialog.exec():
            self._refresh_models()
