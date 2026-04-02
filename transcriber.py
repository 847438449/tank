"""Natural-paragraph transcription worker with GPU-first fallback strategy."""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, Queue
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel

from audio_capture import AudioFrame


@dataclass
class TranscriberConfig:
    model_size: str = "medium"
    language: str = "ja"
    beam_size: int = 5
    condition_on_previous_text: bool = True
    vad_filter: bool = True
    frame_timeout_sec: float = 0.2

    silence_end_sec: float = 1.0
    max_segment_sec: float = 14.0
    min_segment_sec: float = 0.8

    prefer_cuda: bool = True
    cpu_compute_type: str = "int8"
    cuda_compute_type: str = "float16"

    initial_prompt: str = (
        "これは日本語の音声書き起こしです。"
        "自然な日本語の文として出力してください。"
        "句読点を保ち、他言語へ翻訳しないでください。"
    )


@dataclass
class TranscriptSegment:
    timestamp: str
    text: str
    start_sec: float
    end_sec: float


class TranscriptionWorker:
    """Aggregate short frames into natural segments, then transcribe each segment."""

    def __init__(
        self,
        input_queue: Queue,
        output_queue: Queue,
        error_queue: Optional[Queue] = None,
        config: Optional[TranscriberConfig] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.input_queue = input_queue
        self.output_queue = output_queue
        self.error_queue = error_queue
        self.config = config or TranscriberConfig()
        self.logger = logger or logging.getLogger(__name__)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._model: Optional[WhisperModel] = None

        self._segment_frames: list[np.ndarray] = []
        self._segment_duration = 0.0
        self._silence_duration = 0.0
        self._segment_started_at = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.logger.warning("Transcription worker already running.")
            return

        self._stop_event.clear()
        self._load_model_with_fallback()
        self._thread = threading.Thread(target=self._run, name="TranscriberThread", daemon=True)
        self._thread.start()
        self.logger.info("Transcription worker started.")

    def stop(self, timeout: float = 8.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                self.logger.warning("Transcription worker did not exit before timeout.")
            else:
                self.logger.info("Transcription worker stopped.")

    def _load_model_with_fallback(self) -> None:
        if self._model is not None:
            return

        if self.config.prefer_cuda:
            try:
                self.logger.info(
                    "Trying faster-whisper with CUDA: model='%s', compute_type='%s'",
                    self.config.model_size,
                    self.config.cuda_compute_type,
                )
                self._model = WhisperModel(
                    self.config.model_size,
                    device="cuda",
                    compute_type=self.config.cuda_compute_type,
                )
                self.logger.info("Using GPU / CUDA for transcription.")
                return
            except Exception as exc:
                self.logger.exception("CUDA initialization failed, fallback to CPU. Error: %s", exc)
                if self.error_queue is not None:
                    self.error_queue.put("CUDA 初始化失败，已自动回退到 CPU 模式。")

        self.logger.info(
            "Using CPU for transcription: model='%s', compute_type='%s'",
            self.config.model_size,
            self.config.cpu_compute_type,
        )
        self._model = WhisperModel(
            self.config.model_size,
            device="cpu",
            compute_type=self.config.cpu_compute_type,
        )

    def _run(self) -> None:
        assert self._model is not None, "Model must be loaded before worker run."

        while not self._stop_event.is_set():
            try:
                frame = self.input_queue.get(timeout=self.config.frame_timeout_sec)
            except Empty:
                continue

            try:
                if frame is None:
                    self.logger.info("Received capture sentinel, flushing last segment.")
                    self._flush_segment(force=True)
                    break

                self._consume_frame(frame)
            except Exception as exc:
                self.logger.exception("Transcription loop failed while processing a frame.")
                if self.error_queue is not None:
                    self.error_queue.put(f"转写线程异常: {exc}")
            finally:
                self.input_queue.task_done()

        self._flush_segment(force=True)
        self.logger.info("Transcription loop exited.")

    def _consume_frame(self, frame: AudioFrame) -> None:
        if frame.is_speech or self._segment_frames:
            if not self._segment_frames:
                self._segment_started_at = frame.captured_at
                self._silence_duration = 0.0

            self._segment_frames.append(frame.audio)
            self._segment_duration += frame.duration_sec

            if frame.is_speech:
                self._silence_duration = 0.0
            else:
                self._silence_duration += frame.duration_sec

            if self._should_flush_segment():
                self._flush_segment(force=False)

    def _should_flush_segment(self) -> bool:
        if self._segment_duration >= self.config.max_segment_sec:
            return True

        if self._segment_duration >= self.config.min_segment_sec and self._silence_duration >= self.config.silence_end_sec:
            return True

        return False

    def _flush_segment(self, force: bool) -> None:
        if not self._segment_frames:
            return

        if not force and self._segment_duration < self.config.min_segment_sec:
            return

        audio = np.concatenate(self._segment_frames).astype(np.float32)
        segment_start = self._segment_started_at
        segment_end = segment_start + self._segment_duration

        try:
            text = self._transcribe_audio(audio)
            if text:
                ts = datetime.now().strftime("[%H:%M:%S]")
                segment = TranscriptSegment(
                    timestamp=ts,
                    text=text,
                    start_sec=segment_start,
                    end_sec=segment_end,
                )
                self.output_queue.put(segment)
                self.logger.info("Segment transcribed: %s %s", ts, text)
        except Exception as exc:
            self.logger.exception("Failed to transcribe a paragraph segment.")
            if self.error_queue is not None:
                self.error_queue.put(f"转写异常: {exc}")
        finally:
            self._segment_frames.clear()
            self._segment_duration = 0.0
            self._silence_duration = 0.0
            self._segment_started_at = 0.0

    def _transcribe_audio(self, audio: np.ndarray) -> str:
        segments, _ = self._model.transcribe(
            audio,
            language=self.config.language,
            beam_size=self.config.beam_size,
            condition_on_previous_text=self.config.condition_on_previous_text,
            vad_filter=self.config.vad_filter,
            initial_prompt=self.config.initial_prompt,
        )
        lines = [s.text.strip() for s in segments if s.text and s.text.strip()]
        text = " ".join(lines).strip()

        # Rule preference: if model already ends with Japanese punctuation, keep segment boundary naturally.
        if text.endswith(("。", "！", "？", "!", "?")):
            return text
        return text
