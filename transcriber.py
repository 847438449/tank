"""Offline transcription worker using faster-whisper."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, Queue
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel


@dataclass
class TranscriberConfig:
    model_size: str = "small"
    device: str = "cpu"
    compute_type: str = "int8"
    beam_size: int = 1
    language: str = "ja"


class TranscriptionWorker:
    """Consumes audio chunks and pushes timestamped text lines."""

    def __init__(
        self,
        input_queue: Queue,
        output_queue: Queue,
        config: Optional[TranscriberConfig] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.config = config or TranscriberConfig()
        self.logger = logger or logging.getLogger(__name__)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._model: Optional[WhisperModel] = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.logger.warning("Transcription worker already running.")
            return

        self._stop_event.clear()
        self._load_model_once()
        self._thread = threading.Thread(target=self._run, name="TranscriberThread", daemon=True)
        self._thread.start()
        self.logger.info("Transcription worker started.")

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                self.logger.warning("Transcription worker did not exit before timeout.")
            else:
                self.logger.info("Transcription worker stopped.")

    def _load_model_once(self) -> None:
        if self._model is not None:
            return
        self.logger.info(
            "Loading faster-whisper model size='%s' device='%s' compute_type='%s'",
            self.config.model_size,
            self.config.device,
            self.config.compute_type,
        )
        self._model = WhisperModel(
            self.config.model_size,
            device=self.config.device,
            compute_type=self.config.compute_type,
        )

    def _run(self) -> None:
        assert self._model is not None, "Model must be loaded before worker run."

        while not self._stop_event.is_set() or not self.input_queue.empty():
            try:
                chunk = self.input_queue.get(timeout=0.2)
            except Empty:
                continue

            try:
                text = self._transcribe_chunk(chunk)
                if text:
                    timestamp = datetime.now().strftime("[%H:%M:%S]")
                    line = f"{timestamp} {text}"
                    self.output_queue.put(line)
                    self.logger.info("Transcribed line: %s", line)
            except Exception:
                self.logger.exception("Failed to transcribe one audio chunk.")
            finally:
                self.input_queue.task_done()

        self.logger.info("Transcription loop exited.")

    def _transcribe_chunk(self, audio_chunk: np.ndarray) -> str:
        audio_chunk = np.asarray(audio_chunk, dtype=np.float32)

        segments, _info = self._model.transcribe(
            audio_chunk,
            language=self.config.language,
            beam_size=self.config.beam_size,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        lines = [seg.text.strip() for seg in segments if seg.text.strip()]
        return " ".join(lines).strip()
