"""Application entrypoint for Windows system-audio Japanese real-time transcription."""

from __future__ import annotations

import logging
from queue import Empty, Queue
from typing import Optional

from audio_capture import WasapiLoopbackCapture
from file_writer import TranscriptFileWriter
from gui import TranscriberGUI
from transcriber import RecognitionEvent, TranscriberConfig, TranscriptionWorker


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


class AppController:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)

        self.audio_queue: Queue = Queue(maxsize=120)
        self.event_queue: Queue = Queue()
        self.error_queue: Queue = Queue()

        self.transcriber_config = TranscriberConfig(
            model_size="medium",  # switchable: small / medium / large-v3
            language="ja",
            beam_size=8,
            best_of=5,
            temperature=0.0,
            condition_on_previous_text=True,
            vad_filter=True,
            silence_end_sec=0.8,
            min_segment_sec=2.5,
            max_segment_sec=11.0,
            window_sec=7.0,
            overlap_sec=1.0,
            prefer_cuda=True,
        )

        self.capture: Optional[WasapiLoopbackCapture] = None
        self.transcriber: Optional[TranscriptionWorker] = None
        self.writer = TranscriptFileWriter(logging.getLogger("writer"))

        self.gui = TranscriberGUI(on_start=self.start, on_stop=self.stop)
        self._running = False

    def start(self, save_path: str, export_srt: bool) -> bool:
        if self._running:
            self.logger.warning("App already running.")
            return True

        try:
            self.writer.open(save_path, export_srt=export_srt)

            self.capture = WasapiLoopbackCapture(
                output_queue=self.audio_queue,
                error_queue=self.error_queue,
                sample_rate=16000,
                frame_seconds=0.4,
                channels=2,
                silence_rms_threshold=0.008,
                logger=logging.getLogger("audio_capture"),
            )
            self.transcriber = TranscriptionWorker(
                input_queue=self.audio_queue,
                output_queue=self.event_queue,
                error_queue=self.error_queue,
                config=self.transcriber_config,
                logger=logging.getLogger("transcriber"),
            )

            self.transcriber.start()
            self.capture.start()

            self._running = True
            self.gui.set_status("状态：运行中（WASAPI loopback）")
            self._poll_queues()
            self.logger.info("Application started successfully.")
            return True
        except Exception as exc:
            self.logger.exception("Failed to start application.")
            self.gui.set_status(f"状态：启动失败 - {exc}")
            self.stop()
            return False

    def stop(self) -> None:
        if not self._running and self.capture is None and self.transcriber is None:
            return

        self.logger.info("Stopping application...")
        try:
            if self.capture:
                self.capture.stop()
            if self.transcriber:
                self.transcriber.stop()

            # Drain final events before closing files.
            self._drain_event_queue()
        finally:
            self.capture = None
            self.transcriber = None
            self.writer.close()
            self._running = False
            self.gui.set_running_ui(False)
            self.gui.set_status("状态：已停止")
            self.logger.info("Application stopped and resources released.")

    def _poll_queues(self) -> None:
        if not self._running:
            return

        self._drain_event_queue()
        self._drain_error_queue()

        self.gui.root.after(150, self._poll_queues)

    def _drain_event_queue(self) -> None:
        try:
            while True:
                event: RecognitionEvent = self.event_queue.get_nowait()
                if event.kind == "preview":
                    self.gui.append_preview(event.segment.timestamp, event.segment.text)
                elif event.kind == "final":
                    self.writer.write_segment(event.segment)
                    self.gui.append_final(event.segment.timestamp, event.segment.text)
        except Empty:
            pass

    def _drain_error_queue(self) -> None:
        try:
            while True:
                err = self.error_queue.get_nowait()
                self.logger.error("Background error: %s", err)
                self.gui.set_status(f"状态：异常 - {err}")
        except Empty:
            pass

    def run(self) -> None:
        self.gui.run()


if __name__ == "__main__":
    setup_logging()
    AppController().run()
