from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from pathlib import Path

from PySide6.QtCore import QObject, Qt, Signal, Slot
from PySide6.QtWidgets import QApplication

from audio_recorder import AudioRecorder
from config import AppConfig, load_config
from context_manager import build_context_for_request, trim_history
from hotkey_listener import HotkeyManager
from llm.factory import ask_with_fallback, create_provider
from overlay_window import OverlayWindow
from prompt_builder import build_answer_prompt
from router import classify_complexity, configure_model_mapping
from settings_dialog import SettingsDialog
from settings_manager import load_settings, reload_settings, save_settings
from speech_to_text import speech_to_text
from utils.logger import setup_logging


class AppController(QObject):
    signal_open_settings = Signal()
    signal_show_overlay = Signal(str)
    signal_close_overlay = Signal()

    def __init__(self, cfg: AppConfig) -> None:
        super().__init__()
        self.cfg = cfg

        self.overlay_window = OverlayWindow(
            width=cfg.overlay_width,
            height=cfg.overlay_height,
            offset_x=cfg.overlay_offset_x,
            offset_y=cfg.overlay_offset_y,
        )
        self.recorder = AudioRecorder(
            sample_rate=cfg.sample_rate,
            channels=cfg.channels,
            device_index=cfg.asr_device_index,
        )
        self.hotkey_manager: HotkeyManager | None = None
        self.settings_dialog: SettingsDialog | None = None

        self.conversation_history: list[dict] = []
        self.classifier_provider = None
        self.summary_provider = None

        self.signal_open_settings.connect(self._open_settings_dialog_impl)
        self.signal_show_overlay.connect(self.overlay_window.show_message)
        self.signal_close_overlay.connect(self.overlay_window.close_overlay)

        self.rebuild_runtime_from_config(cfg)
        self._init_hotkeys()

    def request_show_overlay(self, text: str) -> None:
        self.signal_show_overlay.emit(text)

    def request_close_overlay(self) -> None:
        self.signal_close_overlay.emit()

    def request_open_settings(self) -> None:
        self.signal_open_settings.emit()

    def rebuild_runtime_from_config(self, new_cfg: AppConfig) -> None:
        self.cfg = new_cfg
        configure_model_mapping(
            cheap_model=self.cfg.cheap_model,
            balanced_model=self.cfg.balanced_model,
            premium_model=self.cfg.premium_model,
        )

        try:
            self.classifier_provider = create_provider(self.cfg, model=self.cfg.classifier_model)
        except Exception:
            logging.exception("Failed to initialize classifier provider")
            self.classifier_provider = None

        try:
            self.summary_provider = create_provider(self.cfg, model=self.cfg.summary_model)
        except Exception:
            logging.exception("Failed to initialize summary provider")
            self.summary_provider = None

    def _init_hotkeys(self) -> None:
        self.hotkey_manager = HotkeyManager(
            record_hotkey=self.cfg.hotkey,
            settings_hotkey=self.cfg.settings_hotkey,
            on_record_press=self.on_record_press,
            on_record_release=self.on_record_release,
            on_settings_press=self.request_open_settings,
        )
        self.hotkey_manager.start()

    @Slot()
    def _open_settings_dialog_impl(self) -> None:
        logging.info("Settings dialog requested")

        if self.recorder.is_recording:
            self.request_show_overlay("请先结束录音后再打开设置")
            return

        if self.settings_dialog is not None and self.settings_dialog.isVisible():
            logging.info("Settings dialog already exists, activating existing window")
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return

        if self.settings_dialog is None:
            self.settings_dialog = SettingsDialog(load_settings())
            self.settings_dialog.settings_saved.connect(self._on_settings_saved)
        else:
            self.settings_dialog.update_settings(load_settings())

        self.settings_dialog.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()
        logging.info("Settings dialog shown")
        logging.info("Settings dialog raised to front")

    @Slot(dict)
    def _on_settings_saved(self, settings: dict) -> None:
        try:
            save_settings(settings)
            latest = reload_settings()
            new_cfg = AppConfig(**{k: v for k, v in latest.items() if k in AppConfig.__dataclass_fields__})
            self.rebuild_runtime_from_config(new_cfg)
            self.recorder = AudioRecorder(
                sample_rate=self.cfg.sample_rate,
                channels=self.cfg.channels,
                device_index=self.cfg.asr_device_index,
            )
            if self.hotkey_manager is not None:
                self.hotkey_manager.reload(self.cfg.hotkey, self.cfg.settings_hotkey)
            self.request_show_overlay("设置已保存并生效")
        except Exception as exc:
            logging.exception("Failed to apply settings")
            self.request_show_overlay(f"设置保存失败: {exc}")

    def on_record_press(self) -> None:
        if self.recorder.is_recording:
            logging.info("Press ignored: already recording")
            return

        try:
            self.recorder.start_recording()
            logging.info("Recording started")
            self.request_show_overlay("正在录音...")
        except Exception:
            logging.exception("on_press failed")
            self.request_show_overlay("录音启动失败")

    def process_audio(self, audio_path: Path) -> None:
        try:
            logging.info("STT started")
            stt_settings = {
                "asr_provider": self.cfg.asr_provider,
                "asr_model_size": self.cfg.asr_model_size,
                "asr_language": self.cfg.asr_language,
                "asr_device": self.cfg.asr_device,
                "asr_compute_type": self.cfg.asr_compute_type,
                "asr_vad_filter": self.cfg.asr_vad_filter,
                "asr_beam_size": self.cfg.asr_beam_size,
                "asr_min_silence_duration_ms": self.cfg.asr_min_silence_duration_ms,
            }
            text = speech_to_text(audio_path, settings=stt_settings)
            logging.info("STT result: %s", text)

            if text in {"未识别到有效语音", "语音识别失败，请重试"}:
                stats = self.recorder.last_audio_stats
                if text == "未识别到有效语音" and stats is not None and stats.near_silence:
                    self.request_show_overlay("没有识别到有效语音，请检查麦克风或提高音量")
                else:
                    self.request_show_overlay(text)
                return

            if not text.strip():
                self.request_show_overlay("未识别到有效语音")
                return

            if self.classifier_provider is None:
                complexity = "medium"
                logging.warning("Classifier provider unavailable, default medium")
            else:
                complexity = classify_complexity(text=text, provider=self.classifier_provider)
            logging.info("Router complexity=%s", complexity)

            request_context = build_context_for_request(
                history=self.conversation_history,
                complexity=complexity,
                provider=self.summary_provider,
            )

            system_prompt = build_answer_prompt(text, complexity)
            self.request_show_overlay("正在思考...")
            logging.info("LLM request started")
            answer, used_model, fallback_triggered = ask_with_fallback(
                user_text=text,
                complexity=complexity,
                config=self.cfg,
                history=request_context,
                system_prompt=system_prompt,
            )

            logging.info(
                "LLM used_model=%s fallback=%s answer_len=%d",
                used_model,
                fallback_triggered,
                len(answer or ""),
            )

            final_answer = (answer or "").strip() or "[llm empty reply]"
            self.request_show_overlay(final_answer)

            self.conversation_history.extend(
                [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": final_answer},
                ]
            )
            self.conversation_history = trim_history(
                self.conversation_history,
                max_turns=self.cfg.max_history_turns,
                max_chars=self.cfg.max_history_chars,
            )
        except Exception:
            logging.exception("process_audio failed")
            self.request_show_overlay("处理失败，请查看日志")

    def on_record_release(self) -> None:
        if not self.recorder.is_recording:
            logging.info("Release ignored: recorder not running")
            return

        try:
            audio_path = self.recorder.stop_recording()
            logging.info("Recording stopped")
            if audio_path is None:
                self.request_show_overlay("未录到音频")
                return

            self.request_show_overlay("正在识别语音...")
            threading.Thread(target=self.process_audio, args=(audio_path,), daemon=True).start()
        except Exception:
            logging.exception("on_release failed")
            self.request_show_overlay("录音停止失败")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug-hotkeys", action="store_true", help="Only listen and print key events")
    return parser.parse_args()


def run_debug_hotkeys(cfg: AppConfig) -> int:
    logging.info("Running in debug-hotkeys mode. No recording/STT/LLM will run.")

    manager = HotkeyManager(
        record_hotkey=cfg.hotkey,
        settings_hotkey=cfg.settings_hotkey,
        on_record_press=lambda: logging.info("Recording started"),
        on_record_release=lambda: logging.info("Recording stopped"),
        on_settings_press=lambda: logging.info("Settings hotkey triggered"),
    )
    manager.start()

    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        logging.info("Debug hotkeys mode stopped by user")
    finally:
        manager.stop()
    return 0


def main() -> int:
    args = parse_args()
    cfg = load_config()
    setup_logging(cfg.log_level)

    if args.debug_hotkeys:
        return run_debug_hotkeys(cfg)

    app = QApplication(sys.argv)

    controller = AppController(cfg)
    controller.request_show_overlay(f"Hold [{cfg.hotkey}] to talk")
    logging.info("App started. Hold [%s] to record.", cfg.hotkey)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
