from __future__ import annotations

import logging
import wave
from pathlib import Path
from typing import Protocol


class SpeechToTextEngine(Protocol):
    """Stable engine interface for swapping STT backends later."""

    def transcribe(self, audio_path: Path) -> str:
        ...


class PlaceholderSTTEngine:
    """Replaceable default STT implementation.

    Current behavior validates wav file and returns a placeholder text.
    Swap this class with real engines (Whisper/Vosk/OpenAI transcription) later.
    """

    def transcribe(self, audio_path: Path) -> str:
        with wave.open(str(audio_path), "rb") as wav:
            n_frames = wav.getnframes()
            frame_rate = wav.getframerate() or 1
            duration = n_frames / frame_rate

        if duration <= 0:
            return "[speech_to_text error] 音频时长为 0 秒"

        return f"[speech_to_text placeholder] 已读取音频 {duration:.2f}s，待接入真实 ASR。"


def speech_to_text(audio_path: str | Path, engine: SpeechToTextEngine | None = None) -> str:
    """Transcribe wav file and return text with stable interface.

    Args:
        audio_path: Path to wav file.
        engine: Optional custom STT backend implementing `transcribe`.

    Returns:
        Recognized text, or explicit error text if recognition fails.
    """
    path = Path(audio_path)
    if not path.exists():
        return f"[speech_to_text error] 文件不存在: {path}"

    if path.suffix.lower() != ".wav":
        return f"[speech_to_text error] 仅支持 wav 文件: {path}"

    backend = engine or PlaceholderSTTEngine()

    try:
        result = (backend.transcribe(path) or "").strip()
        if not result:
            return "[speech_to_text error] 识别结果为空"
        return result
    except wave.Error as exc:
        logging.exception("Invalid wav file: %s", path)
        return f"[speech_to_text error] wav 文件无效: {exc}"
    except Exception as exc:
        logging.exception("speech_to_text failed: %s", path)
        return f"[speech_to_text error] 识别失败: {exc}"
