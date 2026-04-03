from __future__ import annotations

from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLineEdit,
    QMessageBox,
    QSpinBox,
    QTextEdit,
)

from hotkey_listener import parse_hotkey_string


class SettingsDialog(QDialog):
    settings_saved = Signal(dict)

    def __init__(self, settings: dict[str, Any], parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(560)
        self._settings = settings

        layout = QFormLayout(self)

        self.hotkey_input = QLineEdit(settings.get("hotkey", "f8"))
        self.settings_hotkey_input = QLineEdit(settings.get("settings_hotkey", "f10"))
        self.provider_input = QLineEdit(settings.get("llm_provider", "openai"))
        self.classifier_input = QLineEdit(settings.get("classifier_model", "gpt-4o-mini"))
        self.summary_input = QLineEdit(settings.get("summary_model", "gpt-4o-mini"))
        self.cheap_input = QLineEdit(settings.get("cheap_model", "gpt-4o-mini"))
        self.balanced_input = QLineEdit(settings.get("balanced_model", "gpt-5.4-mini"))
        self.premium_input = QLineEdit(settings.get("premium_model", "gpt-5.4"))

        self.timeout_input = QLineEdit(str(settings.get("openai_timeout", 20.0)))
        self.asr_provider_input = QLineEdit(settings.get("asr_provider", "faster_whisper"))
        self.asr_model_size_input = QLineEdit(settings.get("asr_model_size", "small"))
        self.asr_language_input = QLineEdit(settings.get("asr_language", "zh"))
        self.asr_device_input = QLineEdit(settings.get("asr_device", "cpu"))
        self.asr_compute_type_input = QLineEdit(settings.get("asr_compute_type", "int8"))
        self.prompt_input = QTextEdit(settings.get("openai_system_prompt", ""))

        self.turns_input = QSpinBox()
        self.turns_input.setRange(1, 50)
        self.turns_input.setValue(int(settings.get("max_history_turns", 6)))

        self.chars_input = QSpinBox()
        self.chars_input.setRange(200, 20000)
        self.chars_input.setValue(int(settings.get("max_history_chars", 2200)))

        self.log_level_input = QLineEdit(settings.get("log_level", "INFO"))

        layout.addRow("录音热键", self.hotkey_input)
        layout.addRow("设置热键", self.settings_hotkey_input)
        layout.addRow("LLM Provider", self.provider_input)
        layout.addRow("Classifier Model", self.classifier_input)
        layout.addRow("Summary Model", self.summary_input)
        layout.addRow("Cheap Model", self.cheap_input)
        layout.addRow("Balanced Model", self.balanced_input)
        layout.addRow("Premium Model", self.premium_input)
        layout.addRow("Timeout", self.timeout_input)
        layout.addRow("ASR Provider", self.asr_provider_input)
        layout.addRow("ASR Model Size", self.asr_model_size_input)
        layout.addRow("ASR Language", self.asr_language_input)
        layout.addRow("ASR Device", self.asr_device_input)
        layout.addRow("ASR Compute Type", self.asr_compute_type_input)
        layout.addRow("System Prompt", self.prompt_input)
        layout.addRow("Max History Turns", self.turns_input)
        layout.addRow("Max History Chars", self.chars_input)
        layout.addRow("Log Level", self.log_level_input)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.hide)
        layout.addRow(buttons)

    def update_settings(self, settings: dict[str, Any]) -> None:
        self._settings = settings
        self.hotkey_input.setText(settings.get("hotkey", "f8"))
        self.settings_hotkey_input.setText(settings.get("settings_hotkey", "f10"))
        self.provider_input.setText(settings.get("llm_provider", "openai"))
        self.classifier_input.setText(settings.get("classifier_model", "gpt-4o-mini"))
        self.summary_input.setText(settings.get("summary_model", "gpt-4o-mini"))
        self.cheap_input.setText(settings.get("cheap_model", "gpt-4o-mini"))
        self.balanced_input.setText(settings.get("balanced_model", "gpt-5.4-mini"))
        self.premium_input.setText(settings.get("premium_model", "gpt-5.4"))
        self.timeout_input.setText(str(settings.get("openai_timeout", 20.0)))
        self.asr_provider_input.setText(settings.get("asr_provider", "faster_whisper"))
        self.asr_model_size_input.setText(settings.get("asr_model_size", "small"))
        self.asr_language_input.setText(settings.get("asr_language", "zh"))
        self.asr_device_input.setText(settings.get("asr_device", "cpu"))
        self.asr_compute_type_input.setText(settings.get("asr_compute_type", "int8"))
        self.prompt_input.setPlainText(settings.get("openai_system_prompt", ""))
        self.turns_input.setValue(int(settings.get("max_history_turns", 6)))
        self.chars_input.setValue(int(settings.get("max_history_chars", 2200)))
        self.log_level_input.setText(settings.get("log_level", "INFO"))

    def _on_save(self) -> None:
        hotkey = self.hotkey_input.text().strip().lower()
        settings_hotkey = self.settings_hotkey_input.text().strip().lower()

        if hotkey == settings_hotkey:
            QMessageBox.warning(self, "冲突", "录音热键和设置热键不能相同")
            return

        parse_hotkey_string(hotkey, default="f8")
        parse_hotkey_string(settings_hotkey, default="f10")

        try:
            timeout = float(self.timeout_input.text().strip())
            if timeout <= 0:
                raise ValueError("timeout must be positive")
        except Exception:
            QMessageBox.warning(self, "输入错误", "Timeout 必须是正数")
            return

        settings = {
            **self._settings,
            "hotkey": hotkey,
            "settings_hotkey": settings_hotkey,
            "llm_provider": self.provider_input.text().strip() or "openai",
            "classifier_model": self.classifier_input.text().strip(),
            "summary_model": self.summary_input.text().strip(),
            "cheap_model": self.cheap_input.text().strip(),
            "balanced_model": self.balanced_input.text().strip(),
            "premium_model": self.premium_input.text().strip(),
            "openai_timeout": timeout,
            "asr_provider": self.asr_provider_input.text().strip() or "faster_whisper",
            "asr_model_size": self.asr_model_size_input.text().strip() or "small",
            "asr_language": self.asr_language_input.text().strip() or "zh",
            "asr_device": self.asr_device_input.text().strip() or "cpu",
            "asr_compute_type": self.asr_compute_type_input.text().strip() or "int8",
            "openai_system_prompt": self.prompt_input.toPlainText().strip(),
            "max_history_turns": int(self.turns_input.value()),
            "max_history_chars": int(self.chars_input.value()),
            "log_level": self.log_level_input.text().strip() or "INFO",
        }

        self.settings_saved.emit(settings)
        QMessageBox.information(self, "成功", "设置已保存")
        self.hide()
