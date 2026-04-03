"""Windows WASAPI loopback audio capture with Bluetooth-stable mode and non-blocking output."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
import soundcard as sc

from ring_buffer import RingBuffer


@dataclass
class AudioFrame:
    audio: np.ndarray
    is_speech: bool
    duration_sec: float
    captured_at: float


class AudioCaptureError(RuntimeError):
    pass


class WasapiLoopbackCapture:
    def __init__(
        self,
        output_buffer: RingBuffer[AudioFrame | None],
        error_queue,
        sample_rate: int = 48000,
        frame_seconds: float = 0.4,
        channels: int = 2,
        silence_rms_threshold: float = 0.006,
        default_blocksize: int = 1024,
        bluetooth_blocksize: int = 4096,
        bluetooth_mode: bool = True,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.output_buffer = output_buffer
        self.error_queue = error_queue
        self.sample_rate = sample_rate
        self.frame_seconds = frame_seconds
        self.channels = channels
        self.silence_rms_threshold = silence_rms_threshold
        self.default_blocksize = default_blocksize
        self.bluetooth_blocksize = bluetooth_blocksize
        self.bluetooth_mode = bluetooth_mode
        self.logger = logger or logging.getLogger(__name__)

        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, name="AudioCaptureThread", daemon=True)
        self._thread.start()
        self.logger.info("Audio capture started (sample_rate=%d bluetooth_mode=%s).", self.sample_rate, self.bluetooth_mode)

    def stop(self, timeout: float = 4.0) -> None:
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=timeout)

    def _run(self) -> None:
        frames_per_buffer = max(1, int(self.sample_rate * self.frame_seconds))
        expected_duration = frames_per_buffer / self.sample_rate

        try:
            # Re-enumerate every start; do not cache speaker/mic instances.
            speaker = sc.default_speaker()
            if speaker is None:
                raise AudioCaptureError("No default speaker found.")

            speaker_name = str(speaker.name)
            if any(k in speaker_name.lower() for k in ["hands-free", "headset", "免提"]):
                self.logger.warning("Detected likely low-quality BT profile device: '%s'.", speaker_name)
                if self.error_queue is not None:
                    self.error_queue.put("检测到 Hands-Free/Headset/免提 设备，音质与稳定性可能较差。")

            mic = sc.get_microphone(id=speaker_name, include_loopback=True)
            if mic is None:
                raise AudioCaptureError("Unable to create WASAPI loopback microphone.")

            blocksize = self.bluetooth_blocksize if self.bluetooth_mode else self.default_blocksize
            self.logger.info(
                "Loopback bind speaker='%s', sample_rate=%d, blocksize=%d, frame=%.2fs",
                speaker_name,
                self.sample_rate,
                blocksize,
                self.frame_seconds,
            )

            last_ts: Optional[float] = None

            with mic.recorder(samplerate=self.sample_rate, channels=self.channels, blocksize=blocksize) as recorder:
                while not self._stop_event.is_set():
                    data = recorder.record(numframes=frames_per_buffer)
                    now_ts = time.time()

                    # Discontinuity tolerance: insert silence for short capture gaps.
                    if last_ts is not None:
                        gap = now_ts - last_ts
                        if gap > expected_duration * 1.8:
                            missing = int(gap / expected_duration) - 1
                            missing = min(max(missing, 0), 4)
                            for _ in range(missing):
                                self._emit_silence_frame(frames_per_buffer)
                            if missing > 0:
                                self.logger.warning("Capture discontinuity detected; inserted %d silence frame(s).", missing)

                    last_ts = now_ts

                    if data is None or len(data) == 0:
                        self._emit_silence_frame(frames_per_buffer)
                        continue

                    chunk = np.asarray(data, dtype=np.float32)
                    if chunk.ndim > 1:
                        chunk = np.mean(chunk, axis=1)

                    # stitch protection for short underflow
                    if len(chunk) < frames_per_buffer:
                        pad = np.zeros(frames_per_buffer - len(chunk), dtype=np.float32)
                        chunk = np.concatenate([chunk, pad])

                    rms = float(np.sqrt(np.mean(np.square(chunk)) + 1e-12))
                    frame = AudioFrame(
                        audio=chunk,
                        is_speech=rms >= self.silence_rms_threshold,
                        duration_sec=len(chunk) / self.sample_rate,
                        captured_at=now_ts,
                    )
                    self.output_buffer.put(frame)

        except Exception as exc:
            self.logger.exception("Audio capture failed.")
            if self.error_queue is not None:
                self.error_queue.put(f"音频采集异常: {exc}")
        finally:
            self.output_buffer.put(None)
            self.output_buffer.close()
            dropped = self.output_buffer.dropped_items
            if dropped:
                self.logger.warning("Capture ring buffer dropped %d frame(s) due downstream lag.", dropped)

    def _emit_silence_frame(self, numframes: int) -> None:
        chunk = np.zeros(numframes, dtype=np.float32)
        frame = AudioFrame(
            audio=chunk,
            is_speech=False,
            duration_sec=len(chunk) / self.sample_rate,
            captured_at=time.time(),
        )
        self.output_buffer.put(frame)
