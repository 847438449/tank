from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf


class RecorderOpenError(RuntimeError):
    def __init__(self, message: str, user_message: str) -> None:
        super().__init__(message)
        self.user_message = user_message


@dataclass
class AudioStats:
    sample_rate: int
    channels: int
    duration_s: float
    peak: float
    rms: float

    @property
    def near_silence(self) -> bool:
        return self.peak < 0.01 and self.rms < 0.003


def get_default_input_index() -> int | None:
    default_device = sd.default.device
    if isinstance(default_device, (list, tuple)) and len(default_device) > 0:
        idx = default_device[0]
        if idx is not None and idx >= 0:
            return int(idx)
    return None


def get_device_info(device_index: int | None) -> dict | None:
    if device_index is None:
        return None
    try:
        info = sd.query_devices(int(device_index))
        return dict(info)
    except Exception:
        return None


def list_input_devices() -> list[dict]:
    devices = sd.query_devices()
    default_idx = get_default_input_index()
    result = []

    logging.info("Available input devices:")
    for idx, dev in enumerate(devices):
        max_inputs = int(dev.get("max_input_channels", 0))
        if max_inputs <= 0:
            continue

        item = {
            "index": idx,
            "name": dev.get("name", "unknown"),
            "max_input_channels": max_inputs,
            "default_samplerate": float(dev.get("default_samplerate", 0)),
            "is_default": idx == default_idx,
        }
        result.append(item)

        logging.info(
            "#%s: %s inputs=%s default_sr=%.0f%s",
            item["index"],
            item["name"],
            item["max_input_channels"],
            item["default_samplerate"],
            " [default]" if item["is_default"] else "",
        )

    return result


def resolve_input_device(device_index: int | None) -> tuple[int | None, dict | None, str | None]:
    """Return (resolved_index, device_info, warning_msg)."""
    if device_index is not None:
        info = get_device_info(device_index)
        if info and int(info.get("max_input_channels", 0)) > 0:
            return int(device_index), info, None

        warning = "指定麦克风无效，已回退到默认输入设备"
        logging.warning("Requested device index %s is invalid, fallback to default input", device_index)
        default_idx = get_default_input_index()
        default_info = get_device_info(default_idx) if default_idx is not None else None
        return default_idx, default_info, warning

    default_idx = get_default_input_index()
    default_info = get_device_info(default_idx) if default_idx is not None else None
    return default_idx, default_info, None


class AudioRecorder:
    def __init__(self, sample_rate: int = 16000, channels: int = 1, device_index: int | None = None) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._is_recording = False
        self.last_audio_stats: AudioStats | None = None
        self.last_device_notice: str | None = None

    @property
    def is_recording(self) -> bool:
        return self._is_recording

    def _audio_callback(self, indata, frames, time, status) -> None:  # noqa: ANN001
        if status:
            logging.warning("Audio callback status: %s", status)
        self._chunks.append(indata.copy())

    def start_recording(self) -> None:
        if self._is_recording:
            logging.debug("Already recording, start ignored.")
            return

        self._chunks.clear()
        self.last_audio_stats = None
        self.last_device_notice = None

        list_input_devices()
        logging.info("Requested device index: %s", self.device_index)

        resolved_idx, resolved_info, warning_msg = resolve_input_device(self.device_index)
        if warning_msg:
            self.last_device_notice = warning_msg

        if resolved_info is None:
            raise RecorderOpenError(
                "No valid input device found",
                "无法打开当前麦克风，请检查设备编号或系统输入设置",
            )

        resolved_name = resolved_info.get("name", "unknown")
        max_inputs = int(resolved_info.get("max_input_channels", 1))
        default_sr = int(float(resolved_info.get("default_samplerate", self.sample_rate)))

        logging.info("Resolved input device: #%s %s", resolved_idx, resolved_name)

        preferred_channels = max(1, min(self.channels, max_inputs))
        preferred_sr = int(self.sample_rate) if self.sample_rate else default_sr

        attempt_params = [
            {"channels": preferred_channels, "samplerate": preferred_sr},
            {"channels": 1, "samplerate": default_sr},
        ]

        for idx, params in enumerate(attempt_params):
            try:
                logging.info(
                    "Using sample_rate=%s, channels=%s", params["samplerate"], params["channels"]
                )
                self._stream = sd.InputStream(
                    samplerate=params["samplerate"],
                    channels=params["channels"],
                    callback=self._audio_callback,
                    device=resolved_idx,
                )
                self._stream.start()
                self._is_recording = True
                self.sample_rate = int(params["samplerate"])
                self.channels = int(params["channels"])
                logging.info("Recording device opened successfully")
                logging.info("Recording started.")
                return
            except Exception as exc:
                logging.warning("InputStream open failed: %s", exc)
                if idx == 0:
                    logging.warning("InputStream open failed, retrying with device defaults")
                    logging.warning("Retrying with device defaults...")
                else:
                    self._stream = None

        raise RecorderOpenError(
            "Failed to open input device",
            "无法打开当前麦克风，请检查设备编号或系统输入设置",
        )

    def stop_recording(self) -> Path | None:
        if not self._is_recording:
            logging.debug("Not recording, stop ignored.")
            return None

        try:
            assert self._stream is not None
            self._stream.stop()
            self._stream.close()
        except Exception:
            logging.exception("Failed to stop audio stream cleanly.")
        finally:
            self._stream = None
            self._is_recording = False
            logging.info("Recording stopped.")

        if not self._chunks:
            logging.warning("No audio captured.")
            return None

        tmp_file = tempfile.NamedTemporaryFile(prefix="tank_", suffix=".wav", delete=False)
        tmp_path = Path(tmp_file.name)
        tmp_file.close()

        try:
            audio = np.concatenate(self._chunks, axis=0)
            sf.write(tmp_path, audio, self.sample_rate, subtype="PCM_16")

            peak = float(np.max(np.abs(audio)))
            rms = float(np.sqrt(np.mean(np.square(audio))))
            duration_s = float(len(audio) / self.sample_rate)
            self.last_audio_stats = AudioStats(
                sample_rate=self.sample_rate,
                channels=self.channels,
                duration_s=duration_s,
                peak=peak,
                rms=rms,
            )

            logging.info("Audio saved to %s", tmp_path)
            logging.info(
                "Audio stats: sr=%s channels=%s duration=%.2fs peak=%.4f rms=%.4f",
                self.sample_rate,
                self.channels,
                duration_s,
                peak,
                rms,
            )
            if self.last_audio_stats.near_silence:
                logging.warning("Input audio level is too low")

            return tmp_path
        except Exception:
            logging.exception("Failed writing wav file.")
            return None
