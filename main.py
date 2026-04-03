from __future__ import annotations

import logging
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QTimer
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


def main() -> int:
    cfg = load_config()
    setup_logging(cfg.log_level)

    app = QApplication(sys.argv)

    overlay = OverlayWindow(
        width=cfg.overlay_width,
        height=cfg.overlay_height,
        offset_x=cfg.overlay_offset_x,
        offset_y=cfg.overlay_offset_y,
    )
    recorder = AudioRecorder(sample_rate=cfg.sample_rate, channels=cfg.channels)

    conversation_history: list[dict] = []
    classifier_provider = None
    summary_provider = None
    hotkey_manager: HotkeyManager | None = None

    def rebuild_runtime_from_config(new_cfg: AppConfig) -> None:
        nonlocal cfg, classifier_provider, summary_provider
        cfg = new_cfg
        configure_model_mapping(
            cheap_model=cfg.cheap_model,
            balanced_model=cfg.balanced_model,
            premium_model=cfg.premium_model,
        )

        try:
            classifier_provider = create_provider(cfg, model=cfg.classifier_model)
        except Exception:
            logging.exception("Failed to initialize classifier provider")
            classifier_provider = None

        try:
            summary_provider = create_provider(cfg, model=cfg.summary_model)
        except Exception:
            logging.exception("Failed to initialize summary provider")
            summary_provider = None

    rebuild_runtime_from_config(cfg)

    def show_settings_dialog() -> None:
        nonlocal hotkey_manager

        if recorder.is_recording:
            overlay.show_message("请先结束录音后再打开设置")
            return

        logging.info("Settings hotkey triggered")
        dialog = SettingsDialog(load_settings())
        if dialog.exec() != SettingsDialog.DialogCode.Accepted:
            return

        if dialog.saved_settings is None:
            return

        try:
            save_settings(dialog.saved_settings)
            latest_settings = reload_settings()
            new_cfg = AppConfig(**{k: v for k, v in latest_settings.items() if k in AppConfig.__dataclass_fields__})
            rebuild_runtime_from_config(new_cfg)
            if hotkey_manager is not None:
                hotkey_manager.reload(cfg.hotkey, cfg.settings_hotkey)
            overlay.show_message("设置已保存并生效")
        except Exception as exc:
            logging.exception("Failed to apply settings")
            overlay.show_message(f"设置保存失败: {exc}")

    def on_press() -> None:
        if recorder.is_recording:
            logging.info("Press ignored: already recording")
            return

        try:
            recorder.start_recording()
            logging.info("Recording started")
            overlay.show_message("🎤 Recording...")
        except Exception:
            logging.exception("on_press failed")
            overlay.show_message("录音启动失败")

    def process_audio(audio_path: Path) -> None:
        nonlocal conversation_history

        try:
            logging.info("STT started")
            text = speech_to_text(audio_path)
            logging.info("STT result: %s", text)

            if text.startswith("[speech_to_text error]"):
                overlay.show_message(text)
                return

            if not text.strip():
                overlay.show_message("未识别到有效文本")
                return

            if classifier_provider is None:
                complexity = "medium"
                logging.warning("Classifier provider unavailable, default medium")
            else:
                complexity = classify_complexity(text=text, provider=classifier_provider)
            logging.info("Router complexity=%s", complexity)

            request_context = build_context_for_request(
                history=conversation_history,
                complexity=complexity,
                provider=summary_provider,
            )

            system_prompt = build_answer_prompt(text, complexity)
            logging.info("LLM request started")
            answer, used_model, fallback_triggered = ask_with_fallback(
                user_text=text,
                complexity=complexity,
                config=cfg,
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
            overlay.show_message(final_answer)

            conversation_history.extend(
                [
                    {"role": "user", "content": text},
                    {"role": "assistant", "content": final_answer},
                ]
            )
            conversation_history = trim_history(
                conversation_history,
                max_turns=cfg.max_history_turns,
                max_chars=cfg.max_history_chars,
            )
        except Exception:
            logging.exception("process_audio failed")
            overlay.show_message("处理失败，请查看日志")

    def on_release() -> None:
        if not recorder.is_recording:
            logging.info("Release ignored: recorder not running")
            return

        try:
            audio_path = recorder.stop_recording()
            logging.info("Recording stopped")
            if audio_path is None:
                overlay.show_message("未录到音频")
                return

            overlay.show_message("⏳ 正在识别与请求模型...")
            threading.Thread(target=process_audio, args=(audio_path,), daemon=True).start()
        except Exception:
            logging.exception("on_release failed")
            overlay.show_message("录音停止失败")

    hotkey_manager = HotkeyManager(
        record_hotkey=cfg.hotkey,
        settings_hotkey=cfg.settings_hotkey,
        on_record_press=on_press,
        on_record_release=on_release,
        on_settings_press=lambda: QTimer.singleShot(0, show_settings_dialog),
    )

    try:
        hotkey_manager.start()
    except Exception:
        logging.exception("Hotkey listener startup failed")
        overlay.show_message("热键监听启动失败，请尝试管理员权限运行")

    logging.info("App started. Hold [%s] to record.", cfg.hotkey)
    overlay.show_message(f"Hold [{cfg.hotkey}] to talk")
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
