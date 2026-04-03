from __future__ import annotations

import logging
import tempfile
from pathlib import Path

import sounddevice as sd
import soundfile as sf


class AudioRecorder:
    """Simple push-to-talk recorder with temp WAV output."""

    def __init__(self, sample_rate: int = 16000, channels: int = 1) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self._stream: sd.InputStream | None = None
        self._chunks: list = []
        self._is_recording = False

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
        try:
            self._stream = sd.InputStream(
                samplerate=self.sample_rate,
                channels=self.channels,
                callback=self._audio_callback,
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

        if not self._chunks:
            logging.warning("No audio captured.")
            return None

        tmp_file = tempfile.NamedTemporaryFile(prefix="tank_", suffix=".wav", delete=False)
        tmp_path = Path(tmp_file.name)
        tmp_file.close()

        try:
            import numpy as np

            audio = np.concatenate(self._chunks, axis=0)
            sf.write(tmp_path, audio, self.sample_rate, subtype="PCM_16")
            logging.info("Recording saved to %s", tmp_path)
            return tmp_path
        except Exception:
            logging.exception("Failed writing wav file.")
            return None
