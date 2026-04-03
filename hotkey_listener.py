from __future__ import annotations

import logging
from typing import Callable

import keyboard


class PushToTalkHotkey:
    """Listen for key press/release globally on Windows."""

    def __init__(
        self,
        hotkey: str,
        on_press: Callable[[], None],
        on_release: Callable[[], None],
    ) -> None:
        self.hotkey = hotkey
        self.on_press = on_press
        self.on_release = on_release
        self._press_hook = None
        self._release_hook = None

    def start(self) -> None:
        try:
            self._press_hook = keyboard.on_press_key(self.hotkey, lambda _: self.on_press())
            self._release_hook = keyboard.on_release_key(self.hotkey, lambda _: self.on_release())
            logging.info("Hotkey listener started: %s", self.hotkey)
        except Exception:
            logging.exception("Failed to register hotkey %s", self.hotkey)
            raise

    def stop(self) -> None:
        try:
            if self._press_hook is not None:
                keyboard.unhook(self._press_hook)
            if self._release_hook is not None:
                keyboard.unhook(self._release_hook)
        except Exception:
            logging.exception("Failed to unhook hotkey listener")

    @staticmethod
    def wait_forever() -> None:
        keyboard.wait()
