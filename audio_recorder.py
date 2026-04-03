from __future__ import annotations

import logging
import tempfile
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import sounddevice as sd
import soundfile as sf


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


def list_input_devices() -> list[dict]:
    devices = sd.query_devices()
    result = []
    for idx, dev in enumerate(devices):
        if dev.get("max_input_channels", 0) > 0:
            result.append(
                {
                    "index": idx,
                    "name": dev.get("name", "unknown"),
                    "max_input_channels": dev.get("max_input_channels", 0),
                    "default_samplerate": dev.get("default_samplerate", 0),
                }
            )
    return result


class AudioRecorder:
    """Simple push-to-talk recorder with temp WAV output."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1, device_index: int | None = None) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.device_index = device_index
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._is_recording = False
        self.last_audio_stats: AudioStats | None = None

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

        try:
            if self.device_index is not None:
                dev_name = sd.query_devices(self.device_index).get("name", "unknown")
                logging.info("Using input device #%s: %s", self.device_index, dev_name)
            else:
                default_dev = sd.query_devices(kind="input")
                logging.info("Using default input device: %s", default_dev.get("name", "unknown"))

            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=self._audio_callback,
                device=self.device_index,
            )
            self._stream.start()
            self._is_recording = True
            logging.info("Recording started.")
        except Exception:
            self._stream = None
            logging.exception("Failed to start recording.")
            raise

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
