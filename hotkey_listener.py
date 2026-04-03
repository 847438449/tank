from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Callable

try:
    from pynput import keyboard  # type: ignore

    HAS_PYNPUT = True
except Exception:  # pragma: no cover
    HAS_PYNPUT = False

    class _DummyKey:
        def __init__(self, name: str) -> None:
            self.name = name

        def __repr__(self) -> str:
            return self.name

        def __eq__(self, other: object) -> bool:
            return isinstance(other, _DummyKey) and self.name == other.name

    class _DummyKeyCode:
        def __init__(self, char: str | None = None) -> None:
            self.char = char

        def __repr__(self) -> str:
            return f"KeyCode({self.char})"

    class _DummyKeyboard:
        Key = type(
            "Key",
            (),
            {
                "esc": _DummyKey("esc"),
                "space": _DummyKey("space"),
                "enter": _DummyKey("enter"),
                "tab": _DummyKey("tab"),
                **{f"f{i}": _DummyKey(f"f{i}") for i in range(1, 13)},
            },
        )
        KeyCode = _DummyKeyCode

        class Listener:  # pragma: no cover
            def __init__(self, on_press=None, on_release=None) -> None:  # noqa: ANN001
                self.on_press = on_press
                self.on_release = on_release

            def start(self) -> None:
                raise RuntimeError("pynput is not installed")

            def stop(self) -> None:
                return

    keyboard = _DummyKeyboard()  # type: ignore


@dataclass(frozen=True)
class ParsedHotkey:
    raw: str
    is_special: bool
    special_key: object | None = None
    char: str | None = None

    @property
    def normalized(self) -> str:
        return self.raw.strip().lower()


SPECIAL_KEY_MAP: dict[str, object] = {
    "esc": keyboard.Key.esc,
    "escape": keyboard.Key.esc,
    "space": keyboard.Key.space,
    "enter": keyboard.Key.enter,
    "tab": keyboard.Key.tab,
}
SPECIAL_KEY_MAP.update({f"f{i}": getattr(keyboard.Key, f"f{i}") for i in range(1, 13)})


def parse_hotkey_string(hotkey: str) -> ParsedHotkey:
    text = (hotkey or "").strip().lower()
    if not text:
        raise ValueError("hotkey cannot be empty")

    if text in SPECIAL_KEY_MAP:
        return ParsedHotkey(raw=text, is_special=True, special_key=SPECIAL_KEY_MAP[text])

    if len(text) == 1 and "a" <= text <= "z":
        return ParsedHotkey(raw=text, is_special=False, char=text)

    raise ValueError(f"Unsupported hotkey: {hotkey}")


class HotkeyManager:
    """Global hotkey manager using pynput for reliable function-key handling on Windows."""

    def __init__(
        self,
        record_hotkey: str,
        settings_hotkey: str,
        on_record_press: Callable[[], None],
        on_record_release: Callable[[], None],
        on_settings_press: Callable[[], None],
    ) -> None:
        self.record_hotkey = parse_hotkey_string(record_hotkey)
        self.settings_hotkey = parse_hotkey_string(settings_hotkey)

        if self.record_hotkey.normalized == self.settings_hotkey.normalized:
            raise ValueError("record hotkey and settings hotkey cannot be identical")

        self.on_record_press = on_record_press
        self.on_record_release = on_record_release
        self.on_settings_press = on_settings_press

        self._listener = None
        self._record_down = False
        self._settings_down = False

    def _match(self, pressed_key: object, target: ParsedHotkey) -> bool:
        if target.is_special:
            return pressed_key == target.special_key

        char = getattr(pressed_key, "char", None)
        return (char or "").lower() == target.char

    def _on_press(self, key: object) -> None:
        logging.info("key pressed: %s", key)

        if self._match(key, self.record_hotkey):
            logging.info("hotkey matched on press")
            if not self._record_down:
                self._record_down = True
                self.on_record_press()
            return

        if self._match(key, self.settings_hotkey):
            logging.info("settings hotkey matched on press")
            if not self._settings_down:
                self._settings_down = True
                self.on_settings_press()

    def _on_release(self, key: object) -> None:
        logging.info("key released: %s", key)

        if self._match(key, self.record_hotkey):
            logging.info("hotkey matched on release")
            if self._record_down:
                self._record_down = False
                self.on_record_release()
            return

        if self._match(key, self.settings_hotkey):
            logging.info("settings hotkey matched on release")
            self._settings_down = False

    def start(self) -> None:
        if self._listener is not None:
            return

        if not HAS_PYNPUT:
            raise RuntimeError("pynput is not installed, cannot start global hotkey listener")

        self._listener = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()
        logging.info(
            "Hotkey listener started: record=%s settings=%s",
            self.record_hotkey.normalized,
            self.settings_hotkey.normalized,
        )

    def stop(self) -> None:
        if self._listener is None:
            return
        self._listener.stop()
        self._listener = None
        self._record_down = False
        self._settings_down = False

    def reload(self, record_hotkey: str, settings_hotkey: str) -> None:
        self.stop()
        self.record_hotkey = parse_hotkey_string(record_hotkey)
        self.settings_hotkey = parse_hotkey_string(settings_hotkey)
        if self.record_hotkey.normalized == self.settings_hotkey.normalized:
            raise ValueError("record hotkey and settings hotkey cannot be identical")
        self.start()
        logging.info("Hotkeys reloaded")
