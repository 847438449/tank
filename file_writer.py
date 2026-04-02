"""Append transcription lines safely to local txt files."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional


class TranscriptFileWriter:
    def __init__(self, logger: Optional[logging.Logger] = None) -> None:
        self.logger = logger or logging.getLogger(__name__)
        self._file = None
        self.path: Optional[Path] = None

    @staticmethod
    def default_filename() -> str:
        return f"transcript_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"

    def open(self, path: str | Path) -> None:
        self.close()
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._file = self.path.open("a", encoding="utf-8", buffering=1)
        self.logger.info("Opened transcript file: %s", self.path)

    def write_line(self, line: str) -> None:
        if self._file is None:
            raise RuntimeError("Transcript file is not opened.")
        self._file.write(line + "\n")
        self._file.flush()

    def close(self) -> None:
        if self._file:
            self._file.flush()
            self._file.close()
            self.logger.info("Closed transcript file: %s", self.path)
        self._file = None
