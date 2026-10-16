"""API connections dialog: keys, base URL and model selection per provider."""

from __future__ import annotations

from PySide6.QtWidgets import (QComboBox, QDialog, QDialogButtonBox, QFormLayout, QLabel,
                               QLineEdit, QMessageBox, QPushButton, QVBoxLayout)

from ..core import i18n, providers
from ..core.settings import Settings


class ApiSettingsDialog(QDialog):
    def __init__(self, settings: Settings, parent=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.setWindowTitle(i18n.t("dlg.title"))
        self.setMinimumWidth(460)

        layout = QVBoxLayout(self)
        self.provider_box = QComboBox()
        self.provider_box.addItems(providers.provider_ids())
        self.provider_label = QLabel(i18n.t("ui.label.provider"))
        layout.addWidget(self.provider_label)
        layout.addWidget(self.provider_box)

        form = QFormLayout()
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.base_edit = QLineEdit()
        self.model_edit = QLineEdit()
        form.addRow(i18n.t("dlg.api_key"), self.key_edit)
        form.addRow(i18n.t("dlg.base_url"), self.base_edit)
        form.addRow(i18n.t("ui.label.model"), self.model_edit)
        layout.addLayout(form)

        self.hint = QLabel()
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)

        self.validate_button = QPushButton(i18n.t("dlg.validate"))
        self.validate_button.clicked.connect(self._validate)
        layout.addWidget(self.validate_button)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save
                                   | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.provider_box.currentTextChanged.connect(self._load_provider)
        self._load_provider(self.provider_box.currentText())

    def _load_provider(self, provider_id: str) -> None:
        entry = providers.get_provider(provider_id)
        saved = self.settings.provider(provider_id)
        self.key_edit.setText(self.settings.provider_key(provider_id))
        self.base_edit.setText(str(saved.get("baseUrl") or ""))
        self.base_edit.setEnabled(bool(entry and entry.needs_base_url))
        self.model_edit.setText(str(saved.get("model") or ""))
        self.hint.setText(i18n.t("dlg.key_page", url=entry.key_page)
                          if entry and entry.key_page else i18n.t("dlg.key_optional"))

    def _validate(self) -> None:
        provider_id = self.provider_box.currentText()
        try:
            models = providers.fetch_models(provider_id, self.key_edit.text().strip(),
                                            self.settings, self.base_edit.text().strip())
        except ValueError as exc:
            QMessageBox.warning(self, i18n.t("dlg.validate_failed"), str(exc))
            return
        if models:
            self.model_edit.setText(models[0])
        QMessageBox.information(self, i18n.t("dlg.connected"),
                                i18n.t("dlg.models_found", count=len(models)))

    def _save(self) -> None:
        provider_id = self.provider_box.currentText()
        self.settings.set_provider_key(provider_id, self.key_edit.text().strip())
        entry = self.settings.provider(provider_id)
        entry["baseUrl"] = self.base_edit.text().strip()
        entry["model"] = self.model_edit.text().strip()
        self.settings.save()
        self.accept()
