"""System audio capture module for Windows WASAPI loopback."""

from __future__ import annotations

import logging
import threading
from queue import Queue
from typing import Optional

import numpy as np
import soundcard as sc


class AudioCaptureError(RuntimeError):
    """Raised when audio capture initialization fails."""


class WasapiLoopbackCapture:
    """Capture Windows system output audio through WASAPI loopback."""

    def __init__(
        self,
        output_queue: Queue,
        sample_rate: int = 16000,
        chunk_seconds: int = 5,
        channels: int = 1,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.output_queue = output_queue
        self.sample_rate = sample_rate
        self.chunk_seconds = chunk_seconds
        self.channels = channels
        self.logger = logger or logging.getLogger(__name__)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.logger.warning("Audio capture already running.")
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="AudioCaptureThread", daemon=True)
        self._thread.start()
        self.logger.info("Audio capture thread started.")

    def stop(self, timeout: float = 3.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                self.logger.warning("Audio capture thread did not exit before timeout.")
            else:
                self.logger.info("Audio capture thread stopped.")

    def _run(self) -> None:
        speaker = sc.default_speaker()
        if speaker is None:
            raise AudioCaptureError("No default speaker found. Cannot start WASAPI loopback capture.")

        mic = sc.get_microphone(id=str(speaker.name), include_loopback=True)
        if mic is None:
            raise AudioCaptureError("Failed to get loopback microphone from default speaker.")

        frames_per_chunk = int(self.sample_rate * self.chunk_seconds)

        self.logger.info(
            "Starting WASAPI loopback: speaker='%s', sample_rate=%d, chunk_seconds=%d, channels=%d",
            speaker.name,
            self.sample_rate,
            self.chunk_seconds,
            self.channels,
        )

        try:
            with mic.recorder(
                samplerate=self.sample_rate,
                channels=self.channels,
                blocksize=1024,
            ) as recorder:
                while not self._stop_event.is_set():
                    data = recorder.record(numframes=frames_per_chunk)
                    if data is None or len(data) == 0:
                        self.logger.debug("Empty audio chunk captured, skip.")
                        continue

                    chunk = np.asarray(data, dtype=np.float32)
                    if chunk.ndim > 1:
                        chunk = np.mean(chunk, axis=1)

                    self.output_queue.put(chunk)
                    self.logger.debug("Captured audio chunk frames=%d", len(chunk))

        except Exception:
            self.logger.exception("System audio capture loop exited with error.")
            raise
        finally:
            self.logger.info("WASAPI loopback capture exited.")
