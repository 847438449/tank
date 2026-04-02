"""Transcription pipeline with preprocessing, hybrid segmentation, and GPU->CPU fallback."""

from __future__ import annotations

import logging
import re
import threading
from dataclasses import dataclass, field
from datetime import datetime
from queue import Empty, Queue
from typing import Optional

import numpy as np
from faster_whisper import WhisperModel
from scipy.signal import butter, lfilter, resample_poly

from audio_capture import AudioFrame


GPU_ERROR_KEYWORDS = ("cuda", "cudnn", "cublas", "device-side", "out of memory")


@dataclass
class TranscriberConfig:
    model_size: str = "medium"  # can switch: small / medium / large-v3
    language: str = "ja"

    # High-accuracy pass (final file output)
    beam_size: int = 8
    best_of: int = 5
    temperature: float = 0.0
    condition_on_previous_text: bool = True
    vad_filter: bool = True

    # Fast pass (GUI preview)
    fast_beam_size: int = 2
    fast_best_of: int = 2
    fast_temperature: float = 0.2

    # Segmentation
    frame_timeout_sec: float = 0.2
    silence_end_sec: float = 0.8
    min_segment_sec: float = 2.5
    max_segment_sec: float = 11.0

    # Sliding window for long segments
    window_sec: float = 7.0
    overlap_sec: float = 1.0

    # Device
    prefer_cuda: bool = True
    cuda_compute_type: str = "float16"
    cpu_compute_type: str = "int8"

    # Preprocess
    target_sample_rate: int = 16000
    normalize_rms_target: float = 0.08
    bandpass_low_hz: float = 100.0
    bandpass_high_hz: float = 3800.0

    # Optional replacement dictionary (can be extended)
    correction_dict: dict[str, str] = field(default_factory=dict)

    initial_prompt: str = (
        "これは日本語の動画音声の文字起こしです。"
        "自然な日本語として出力してください。"
        "句読点を適切に補い、不要な繰り返しは減らし、"
        "固有名詞やカタカナ語をできるだけ正確に保ってください。"
    )


@dataclass
class TranscriptSegment:
    timestamp: str
    text: str
    start_sec: float
    end_sec: float


@dataclass
class RecognitionEvent:
    kind: str  # "preview" | "final"
    segment: TranscriptSegment


class TranscriptionWorker:
    """Aggregate frames into natural paragraphs and run two-stage transcription."""

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

        self._using_cuda = False
        self._segment_frames: list[np.ndarray] = []
        self._segment_duration = 0.0
        self._segment_started_at = 0.0
        self._tail_silence = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            self.logger.warning("Transcription worker already running.")
            return

        self._stop_event.clear()
        self._load_model_with_fallback()
        self._thread = threading.Thread(target=self._run, name="TranscriberThread", daemon=True)
        self._thread.start()
        self.logger.info("Transcription worker started.")

    def stop(self, timeout: float = 10.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)
            if self._thread.is_alive():
                self.logger.warning("Transcription worker did not exit before timeout.")
            else:
                self.logger.info("Transcription worker stopped.")

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                frame = self.input_queue.get(timeout=self.config.frame_timeout_sec)
            except Empty:
                continue

            try:
                if frame is None:
                    self.logger.info("Capture sentinel received. Flushing final segment.")
                    self._flush_segment(force=True)
                    break

                self._consume_frame(frame)
            except Exception as exc:
                self.logger.exception("Transcription loop frame processing failed.")
                self._push_error(f"转写线程异常: {exc}")
            finally:
                self.input_queue.task_done()

        self._flush_segment(force=True)
        self.logger.info("Transcription loop exited.")

    def _consume_frame(self, frame: AudioFrame) -> None:
        if frame.is_speech or self._segment_frames:
            if not self._segment_frames:
                self._segment_started_at = frame.captured_at
                self._tail_silence = 0.0

            self._segment_frames.append(frame.audio)
            self._segment_duration += frame.duration_sec

            if frame.is_speech:
                self._tail_silence = 0.0
            else:
                self._tail_silence += frame.duration_sec

            if self._should_cut_segment():
                self._flush_segment(force=False)

    def _should_cut_segment(self) -> bool:
        if self._segment_duration >= self.config.max_segment_sec:
            return True
        if (
            self._segment_duration >= self.config.min_segment_sec
            and self._tail_silence >= self.config.silence_end_sec
        ):
            return True
        return False

    def _flush_segment(self, force: bool) -> None:
        if not self._segment_frames:
            return
        if not force and self._segment_duration < self.config.min_segment_sec:
            return

        raw_audio = np.concatenate(self._segment_frames).astype(np.float32)
        segment_start = self._segment_started_at
        segment_end = segment_start + self._segment_duration

        self._segment_frames.clear()
        self._segment_duration = 0.0
        self._segment_started_at = 0.0
        self._tail_silence = 0.0

        processed = preprocess_audio(
            raw_audio,
            source_sample_rate=self.config.target_sample_rate,
            target_sample_rate=self.config.target_sample_rate,
            normalize_target=self.config.normalize_rms_target,
            bandpass_low_hz=self.config.bandpass_low_hz,
            bandpass_high_hz=self.config.bandpass_high_hz,
        )

        try:
            preview_text = self._transcribe_single_pass(processed, fast_mode=True)
            if preview_text:
                preview_seg = TranscriptSegment(
                    timestamp=datetime.now().strftime("[%H:%M:%S]"),
                    text=postprocess_text(preview_text, self.config.correction_dict),
                    start_sec=segment_start,
                    end_sec=segment_end,
                )
                self.output_queue.put(RecognitionEvent(kind="preview", segment=preview_seg))

            final_text = self._transcribe_with_sliding_windows(processed)
            if not final_text:
                final_text = preview_text

            if final_text:
                final_seg = TranscriptSegment(
                    timestamp=datetime.now().strftime("[%H:%M:%S]"),
                    text=postprocess_text(final_text, self.config.correction_dict),
                    start_sec=segment_start,
                    end_sec=segment_end,
                )
                self.output_queue.put(RecognitionEvent(kind="final", segment=final_seg))

        except Exception as exc:
            self.logger.exception("Segment transcription failed.")
            self._push_error(f"转写异常: {exc}")

    def _transcribe_with_sliding_windows(self, audio: np.ndarray) -> str:
        sr = self.config.target_sample_rate
        win = int(self.config.window_sec * sr)
        overlap = int(self.config.overlap_sec * sr)
        step = max(1, win - overlap)

        if len(audio) <= win:
            return self._transcribe_single_pass(audio, fast_mode=False)

        merged_text = ""
        start = 0
        while start < len(audio):
            end = min(len(audio), start + win)
            window_audio = audio[start:end]
            part = self._transcribe_single_pass(window_audio, fast_mode=False)
            if part:
                merged_text = merge_overlap_text(merged_text, part)
            if end >= len(audio):
                break
            start += step

        return merged_text.strip()

    def _transcribe_single_pass(self, audio: np.ndarray, fast_mode: bool) -> str:
        params = {
            "language": self.config.language,
            "vad_filter": self.config.vad_filter,
            "condition_on_previous_text": self.config.condition_on_previous_text,
            "initial_prompt": self.config.initial_prompt,
        }
        if fast_mode:
            params.update(
                beam_size=self.config.fast_beam_size,
                best_of=self.config.fast_best_of,
                temperature=self.config.fast_temperature,
            )
        else:
            params.update(
                beam_size=self.config.beam_size,
                best_of=self.config.best_of,
                temperature=self.config.temperature,
            )

        return self._transcribe_with_runtime_fallback(audio, **params)

    def _transcribe_with_runtime_fallback(self, audio: np.ndarray, **kwargs: object) -> str:
        try:
            segments, _info = self._model.transcribe(audio, **kwargs)
            lines = [s.text.strip() for s in segments if s.text and s.text.strip()]
            return " ".join(lines).strip()
        except Exception as exc:
            if self._using_cuda and is_gpu_error(exc):
                self.logger.exception("CUDA runtime error detected. Falling back to CPU and retrying current audio.")
                self._push_error("GPU 运行异常，已自动切换 CPU 并重试当前音频。")
                self._switch_to_cpu_model()
                segments, _info = self._model.transcribe(audio, **kwargs)
                lines = [s.text.strip() for s in segments if s.text and s.text.strip()]
                return " ".join(lines).strip()
            raise

    def _load_model_with_fallback(self) -> None:
        if self._model is not None:
            return

        if self.config.prefer_cuda:
            try:
                self.logger.info(
                    "Trying CUDA model: model=%s compute_type=%s",
                    self.config.model_size,
                    self.config.cuda_compute_type,
                )
                self._model = WhisperModel(
                    self.config.model_size,
                    device="cuda",
                    compute_type=self.config.cuda_compute_type,
                )
                self._using_cuda = True
                self.logger.info("Transcriber backend: GPU / CUDA")
                return
            except Exception as exc:
                self.logger.exception("CUDA model init failed. Falling back to CPU.")
                self._push_error(f"CUDA 初始化失败，已自动切换 CPU。错误: {exc}")

        self._switch_to_cpu_model()

    def _switch_to_cpu_model(self) -> None:
        self._model = WhisperModel(
            self.config.model_size,
            device="cpu",
            compute_type=self.config.cpu_compute_type,
        )
        self._using_cuda = False
        self.logger.info("Transcriber backend: CPU")

    def _push_error(self, message: str) -> None:
        if self.error_queue is not None:
            self.error_queue.put(message)


def is_gpu_error(exc: Exception) -> bool:
    text = str(exc).lower()
    return any(k in text for k in GPU_ERROR_KEYWORDS)


def preprocess_audio(
    audio: np.ndarray,
    source_sample_rate: int,
    target_sample_rate: int = 16000,
    normalize_target: float = 0.08,
    bandpass_low_hz: float = 100.0,
    bandpass_high_hz: float = 3800.0,
) -> np.ndarray:
    """Lightweight audio preprocessing for better robustness under background music."""
    x = np.asarray(audio, dtype=np.float32)

    if x.ndim > 1:
        x = np.mean(x, axis=1)

    if source_sample_rate != target_sample_rate:
        gcd = int(np.gcd(source_sample_rate, target_sample_rate))
        up = target_sample_rate // gcd
        down = source_sample_rate // gcd
        x = resample_poly(x, up, down).astype(np.float32)

    x = apply_bandpass(x, target_sample_rate, bandpass_low_hz, bandpass_high_hz)
    x = reduce_background_noise(x)
    x = normalize_rms(x, normalize_target)

    return np.clip(x, -1.0, 1.0).astype(np.float32)


def apply_bandpass(audio: np.ndarray, sample_rate: int, low_hz: float, high_hz: float) -> np.ndarray:
    nyquist = sample_rate * 0.5
    low = max(1e-5, low_hz / nyquist)
    high = min(0.999, high_hz / nyquist)
    if low >= high:
        return audio
    b, a = butter(4, [low, high], btype="band")
    return lfilter(b, a, audio).astype(np.float32)


def reduce_background_noise(audio: np.ndarray) -> np.ndarray:
    # Simple noise gate based on low-percentile energy estimate.
    env = np.abs(audio)
    noise_floor = float(np.percentile(env, 20))
    threshold = noise_floor * 1.8

    attenuated = audio.copy()
    quiet_mask = env < threshold
    attenuated[quiet_mask] *= 0.35
    return attenuated.astype(np.float32)


def normalize_rms(audio: np.ndarray, target_rms: float) -> np.ndarray:
    rms = float(np.sqrt(np.mean(np.square(audio)) + 1e-12))
    if rms <= 1e-7:
        return audio
    gain = target_rms / rms
    return (audio * gain).astype(np.float32)


def merge_overlap_text(existing: str, new_text: str) -> str:
    if not existing:
        return new_text.strip()
    if not new_text:
        return existing.strip()

    ex_tokens = existing.strip().split()
    new_tokens = new_text.strip().split()
    max_k = min(12, len(ex_tokens), len(new_tokens))

    overlap = 0
    for k in range(max_k, 0, -1):
        if ex_tokens[-k:] == new_tokens[:k]:
            overlap = k
            break

    if overlap > 0:
        merged = ex_tokens + new_tokens[overlap:]
        return " ".join(merged).strip()

    # fallback: remove repeated prefix by char-level match
    for i in range(min(len(new_text), 30), 5, -1):
        if existing.endswith(new_text[:i]):
            return (existing + new_text[i:]).strip()

    return f"{existing} {new_text}".strip()


def postprocess_text(text: str, correction_dict: dict[str, str]) -> str:
    s = text.strip()
    if not s:
        return s

    s = remove_repeated_short_phrases(s)
    s = re.sub(r"([。！？、,.!?])\1+", r"\1", s)
    s = re.sub(r"\s+", " ", s).strip()

    for wrong, correct in correction_dict.items():
        s = s.replace(wrong, correct)

    return s


def remove_repeated_short_phrases(text: str) -> str:
    words = text.split()
    if not words:
        return text

    result: list[str] = []
    i = 0
    while i < len(words):
        # detect repeated 1-3 token phrases
        replaced = False
        for span in (3, 2, 1):
            if i + span * 2 > len(words):
                continue
            phrase = words[i : i + span]
            repeat = 1
            while i + span * (repeat + 1) <= len(words) and words[i + span * repeat : i + span * (repeat + 1)] == phrase:
                repeat += 1
            if repeat >= 3:
                result.extend(phrase)
                i += span * repeat
                replaced = True
                break
        if not replaced:
            result.append(words[i])
            i += 1

    return " ".join(result)
