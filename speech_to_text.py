from __future__ import annotations

import logging
from pathlib import Path
from typing import Any


def _load_faster_whisper_model(model_size: str, device: str, compute_type: str):
    from faster_whisper import WhisperModel

    logging.info(
        "Loading ASR model... provider=faster_whisper model=%s device=%s compute=%s",
        model_size,
        device,
        compute_type,
    )
    return WhisperModel(model_size, device=device, compute_type=compute_type)


_MODEL_CACHE: dict[tuple[str, str, str], Any] = {}


def _get_model(model_size: str, device: str, compute_type: str):
    key = (model_size, device, compute_type)
    if key not in _MODEL_CACHE:
        _MODEL_CACHE[key] = _load_faster_whisper_model(model_size, device, compute_type)
    return _MODEL_CACHE[key]


def speech_to_text(audio_path: str | Path, settings: dict | None = None) -> str:
    """Transcribe wav file to real text using local ASR.

    Returns:
        - real recognized text
        - "未识别到有效语音" when empty
        - "语音识别失败，请重试" on failure
    """
    path = Path(audio_path)
    if not path.exists() or path.suffix.lower() != ".wav":
        return "语音识别失败，请重试"

    cfg = settings or {}
    provider = (cfg.get("asr_provider") or "faster_whisper").strip().lower()
    model_size = (cfg.get("asr_model_size") or "small").strip()
    language = (cfg.get("asr_language") or "zh").strip()
    device = (cfg.get("asr_device") or "cpu").strip()
    compute_type = (cfg.get("asr_compute_type") or "int8").strip()

    if provider != "faster_whisper":
        logging.warning("Unsupported ASR provider=%s, fallback to faster_whisper", provider)

    try:
        model = _get_model(model_size=model_size, device=device, compute_type=compute_type)
        segments, _ = model.transcribe(str(path), language=language, vad_filter=True)
        text = "".join((seg.text or "") for seg in segments).strip()

        if not text:
            return "未识别到有效语音"

        logging.info("STT result: %s", text)
        return text
    except ModuleNotFoundError:
        logging.exception("faster-whisper not installed")
        return "语音识别失败，请重试"
    except Exception:
        logging.exception("ASR transcription failed")
        return "语音识别失败，请重试"
