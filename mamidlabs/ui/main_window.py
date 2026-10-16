"""Main window: chat, profile/provider selection, chips and the turn worker."""

from __future__ import annotations

import html
import json
import sys
import threading

from PySide6.QtCore import QThread, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QMainWindow,
                               QMessageBox, QPlainTextEdit, QPushButton, QTextBrowser,
                               QVBoxLayout, QWidget)

from ..core import providers
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
    approval_needed = Signal(str, dict)

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

    def _approve(self, name: str, arguments: dict) -> bool:
        self._approval_result = None
        self._approval_lock.clear()
        self.approval_needed.emit(name, arguments)
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

        self.setWindowTitle("MamidLabs")
        self.resize(980, 720)
        self.setStyleSheet(STYLESHEET)
        self._build_menu()
        self._build_layout()
        self._refresh_models()

    # --- layout --------------------------------------------------------------
    def _build_menu(self) -> None:
        menu = self.menuBar().addMenu("MamidLabs")
        api_action = QAction("API bağlantıları…", self)
        api_action.triggered.connect(self._open_api_settings)
        menu.addAction(api_action)
        quit_action = QAction("Çıkış", self)
        quit_action.triggered.connect(self.close)
        menu.addAction(quit_action)

    def _build_layout(self) -> None:
        central = QWidget()
        layout = QVBoxLayout(central)

        top = QHBoxLayout()
        self.profile_box = QComboBox()
        self.profile_box.addItems([p.label for p in catalog_for_display()])
        self.profile_box.currentIndexChanged.connect(self._on_profile_changed)
        self.provider_box = QComboBox()
        self.provider_box.addItems(["local", *providers.provider_ids()])
        self.provider_box.currentTextChanged.connect(lambda _v: self._refresh_models())
        self.model_box = QComboBox()
        self.start_button = QPushButton("Modeli başlat")
        self.start_button.clicked.connect(self._start_model)
        self.stop_button = QPushButton("Modeli durdur")
        self.stop_button.clicked.connect(lambda: self._manage("stop"))
        for widget in (QLabel("Profil"), self.profile_box, QLabel("Sağlayıcı"), self.provider_box,
                       QLabel("Model"), self.model_box, self.start_button, self.stop_button):
            top.addWidget(widget)
        top.addStretch(1)
        layout.addLayout(top)

        self.chat = QTextBrowser()
        self.chat.setObjectName("chat")
        layout.addWidget(self.chat, 1)

        chips = QHBoxLayout()
        self.internet_chip = QCheckBox("İnternet")
        self.agent_chip = QCheckBox("Ajan")
        self.access_chip = QCheckBox("Tam erişim")
        for chip in (self.internet_chip, self.agent_chip, self.access_chip):
            chip.setChecked(True)
            chips.addWidget(chip)
        chips.addStretch(1)
        layout.addLayout(chips)

        bottom = QHBoxLayout()
        self.input = QPlainTextEdit()
        self.input.setObjectName("input")
        # macOS'ta alışıldık kısayol ⌘+Enter; Ctrl+Enter de çalışsın.
        modifier = "⌘" if sys.platform == "darwin" else "Ctrl"
        self.input.setPlaceholderText(f"Bir mesaj yaz…  ({modifier}+Enter ile gönder)")
        self.input.setFixedHeight(90)
        for sequence in ("Ctrl+Return", "Meta+Return"):
            shortcut = QShortcut(QKeySequence(sequence), self.input)
            shortcut.activated.connect(self._send)
        bottom.addWidget(self.input, 1)
        self.send_button = QPushButton("Gönder")
        self.send_button.clicked.connect(self._send)
        self.stop_turn_button = QPushButton("Durdur")
        self.stop_turn_button.setObjectName("stop")
        self.stop_turn_button.clicked.connect(self._cancel_turn)
        self.stop_turn_button.setEnabled(False)
        bottom.addWidget(self.send_button)
        bottom.addWidget(self.stop_turn_button)
        layout.addLayout(bottom)

        self.setCentralWidget(central)
        self.statusBar().showMessage("Hazır")

    # --- helpers -------------------------------------------------------------
    def _on_profile_changed(self, _index: int) -> None:
        profile = PROFILE_IDS[self.profile_box.currentIndex()] \
            if self.profile_box.currentIndex() < len(PROFILE_IDS) else "max"
        self.settings.local_profile = profile
        self.settings.save()

    def _current_profile(self) -> str:
        return self.settings.local_profile

    def _refresh_models(self) -> None:
        self.model_box.clear()
        provider_id = self.provider_box.currentText()
        if provider_id == "local":
            self.model_box.addItem(f"yerel ({self._current_profile()})")
        else:
            saved = self.settings.provider(provider_id)
            self.model_box.addItem(str(saved.get("model") or "(model seç)"))

    def _append(self, role: str, text: str) -> None:
        colour = {"user": "#8ab4f8", "assistant": "#e6e6e6", "tool": "#9aa0aa",
                  "error": "#ff8a80", "status": "#9aa0aa"}.get(role, "#e6e6e6")
        safe = html.escape(text).replace("\n", "<br>")
        self.chat.append(f'<div style="color:{colour}"><b>{role}:</b> {safe}</div>')

    # --- model management ----------------------------------------------------
    def _manage(self, action: str) -> None:
        if self.manage_worker and self.manage_worker.isRunning():
            return
        self.statusBar().showMessage(f"Model işlemi: {action}…")
        self.manage_worker = ManageWorker(self.manager, action, self._current_profile())
        self.manage_worker.message.connect(self.statusBar().showMessage)
        self.manage_worker.failed.connect(self._on_manage_failed)
        self.manage_worker.start()

    def _start_model(self) -> None:
        self._manage("start")

    def _on_manage_failed(self, text: str) -> None:
        self.statusBar().showMessage("Model işlemi başarısız")
        QMessageBox.warning(self, "Model işlemi başarısız", text)

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
        self.statusBar().showMessage("Yanıt üretiliyor…")
        self.worker.start()

    def _cancel_turn(self) -> None:
        if self.worker and self.worker.isRunning():
            self.worker.cancel()
            self.statusBar().showMessage("Durduruldu")

    def _on_event(self, event: dict) -> None:
        kind = event.get("kind")
        if kind == "answer":
            self._append_streaming(event.get("text", ""))
        elif kind == "thinking":
            self.statusBar().showMessage("Düşünüyor…")
        elif kind == "tool":
            self._append("tool", f"araç: {event.get('tool')}")
        elif kind == "denied":
            self._append("status", "İşlem yapılmadı (izin verilmedi).")
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
        self.statusBar().showMessage("Hazır")

    def _on_approval(self, name: str, arguments: dict) -> None:
        preview = json.dumps(arguments, ensure_ascii=False, indent=2)[:1200]
        answer = QMessageBox.question(
            self, "İzin gerekiyor",
            f"<b>{html.escape(name)}</b> çalıştırılsın mı?<br><pre>{html.escape(preview)}</pre>",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        if self.worker:
            self.worker.resolve_approval(answer == QMessageBox.StandardButton.Yes)

    # --- settings ------------------------------------------------------------
    def _open_api_settings(self) -> None:
        dialog = ApiSettingsDialog(self.settings, self)
        if dialog.exec():
            self._refresh_models()
