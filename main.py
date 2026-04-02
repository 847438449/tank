"""Entry point for Windows system-audio Japanese transcription tool."""

from __future__ import annotations

import logging
from queue import Empty, Queue
from typing import Optional

from audio_capture import WasapiLoopbackCapture
from file_writer import TranscriptFileWriter
from gui import TranscriberGUI
from transcriber import TranscriberConfig, TranscriptionWorker


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    )


class AppController:
    def __init__(self) -> None:
        self.logger = logging.getLogger(self.__class__.__name__)
        self.audio_queue: Queue = Queue(maxsize=8)
        self.text_queue: Queue = Queue()

        # 预留模型大小切换项，默认更稳的 small 模型
        self.transcriber_config = TranscriberConfig(model_size="small", device="cpu", compute_type="int8")

        self.capture: Optional[WasapiLoopbackCapture] = None
        self.transcriber: Optional[TranscriptionWorker] = None
        self.writer = TranscriptFileWriter(logging.getLogger("writer"))

        self.gui = TranscriberGUI(on_start=self.start, on_stop=self.stop)
        self._running = False

    def start(self, save_path: str) -> None:
        if self._running:
            self.logger.warning("App already running.")
            return

        try:
            self.writer.open(save_path)
            self.capture = WasapiLoopbackCapture(
                output_queue=self.audio_queue,
                sample_rate=16000,
                chunk_seconds=5,
                channels=2,
                logger=logging.getLogger("audio_capture"),
            )
            self.transcriber = TranscriptionWorker(
                input_queue=self.audio_queue,
                output_queue=self.text_queue,
                config=self.transcriber_config,
                logger=logging.getLogger("transcriber"),
            )

            self.transcriber.start()
            self.capture.start()

            self._running = True
            self.gui.set_status("状态：运行中（WASAPI loopback）")
            self.gui.set_running_ui(True)
            self._poll_text_queue()
            self.logger.info("Application started successfully.")
        except Exception as exc:
            self.logger.exception("Failed to start application.")
            self.gui.set_status(f"状态：启动失败 - {exc}")
            self.stop()

    def stop(self) -> None:
        if not self._running and not self.capture and not self.transcriber:
            return

        self.logger.info("Stopping application...")
        try:
            if self.capture:
                self.capture.stop()
            if self.transcriber:
                self.transcriber.stop()
        finally:
            self.capture = None
            self.transcriber = None
            self.writer.close()
            self._running = False
            self.gui.set_running_ui(False)
            self.gui.set_status("状态：已停止")
            self.logger.info("Application stopped and resources released.")

    def _poll_text_queue(self) -> None:
        if not self._running:
            return

        try:
            while True:
                line = self.text_queue.get_nowait()
                self.writer.write_line(line)
                self.gui.append_text(line)
        except Empty:
            pass
        finally:
            self.gui.root.after(200, self._poll_text_queue)

    def run(self) -> None:
        self.gui.run()


if __name__ == "__main__":
    setup_logging()
    AppController().run()
