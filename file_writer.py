"""TXT (primary) and optional SRT writer for transcript paragraphs."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from transcriber import TranscriptSegment


class TranscriptFileWriter:
    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self._txt_file = None
        self._srt_file = None
        self.txt_path: Optional[Path] = None
        self.srt_path: Optional[Path] = None
        self._srt_index = 1

    @staticmethod
    def default_filename() -> str:
        return f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    def open(self, txt_path: str | Path, export_srt: bool = False) -> None:
        self.close()

        self.txt_path = Path(txt_path)
        self.txt_path.parent.mkdir(parents=True, exist_ok=True)
        self._txt_file = self.txt_path.open("a", encoding="utf-8", buffering=1)
        self.logger.info("Opened txt transcript file: %s", self.txt_path)

        if export_srt:
            self.srt_path = self.txt_path.with_suffix(".srt")
            self._srt_file = self.srt_path.open("a", encoding="utf-8", buffering=1)
            self._srt_index = 1
            self.logger.info("Opened optional srt file: %s", self.srt_path)

    def write_segment(self, segment: TranscriptSegment) -> None:
        if self._txt_file is None:
            raise RuntimeError("TXT transcript file is not opened.")

        self._txt_file.write(f"{segment.timestamp}\n{segment.text}\n\n")
        self._txt_file.flush()

        if self._srt_file is not None:
            start = self._format_srt_time(segment.start_sec)
            end = self._format_srt_time(segment.end_sec)
            self._srt_file.write(f"{self._srt_index}\n{start} --> {end}\n{segment.text}\n\n")
            self._srt_file.flush()
            self._srt_index += 1

    def close(self) -> None:
        if self._txt_file:
            self._txt_file.flush()
            self._txt_file.close()
            self.logger.info("Closed txt transcript file: %s", self.txt_path)

        if self._srt_file:
            self._srt_file.flush()
            self._srt_file.close()
            self.logger.info("Closed srt transcript file: %s", self.srt_path)

        self._txt_file = None
        self._srt_file = None
        self.txt_path = None
        self.srt_path = None

    @staticmethod
    def _format_srt_time(seconds: float) -> str:
        total_ms = int(max(0.0, seconds) * 1000)
        ms = total_ms % 1000
        sec = (total_ms // 1000) % 60
        minute = (total_ms // 60000) % 60
        hour = total_ms // 3600000
        return f"{hour:02d}:{minute:02d}:{sec:02d},{ms:03d}"
