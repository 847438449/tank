from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from typing import Callable

try:
    from pynput import keyboard as pynput_keyboard  # type: ignore

    HAS_PYNPUT = True
except Exception:  # pragma: no cover
    HAS_PYNPUT = False
    pynput_keyboard = None  # type: ignore

try:
    import keyboard as keyboard_lib  # type: ignore

    HAS_KEYBOARD = True
except Exception:  # pragma: no cover
    HAS_KEYBOARD = False
    keyboard_lib = None  # type: ignore


@dataclass(frozen=True)
class ParsedHotkey:
    raw: str
    is_special: bool
    key_name: str

    @property
    def normalized(self) -> str:
        return self.raw.strip().lower()


SUPPORTED_SPECIAL = {"esc", "enter", "tab", "space", *{f"f{i}" for i in range(1, 13)}}


def parse_hotkey_string(text: str, default: str = "f8") -> ParsedHotkey:
    raw = (text or "").strip().lower()

    def _fallback() -> ParsedHotkey:
        d = default.strip().lower()
        is_special = d in SUPPORTED_SPECIAL
        return ParsedHotkey(raw=d, is_special=is_special, key_name=d)

    if not raw:
        logging.warning("Empty hotkey config, fallback to %s", default)
        return _fallback()

    if raw in SUPPORTED_SPECIAL:
        return ParsedHotkey(raw=raw, is_special=True, key_name=raw)

    if len(raw) == 1 and "a" <= raw <= "z":
        return ParsedHotkey(raw=raw, is_special=False, key_name=raw)

    logging.warning("Unsupported hotkey '%s', fallback to %s", text, default)
    return _fallback()


class _BaseHotkeyListener:
    def start(self) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        raise NotImplementedError

    @property
    def events_count(self) -> int:
        raise NotImplementedError


class PynputHotkeyListener(_BaseHotkeyListener):
    def __init__(
        self,
        record_hotkey: ParsedHotkey,
        settings_hotkey: ParsedHotkey,
        on_record_press: Callable[[], None],
        on_record_release: Callable[[], None],
        on_settings_press: Callable[[], None],
    ) -> None:
        if not HAS_PYNPUT:
            raise RuntimeError("pynput is not installed")

        self.record_hotkey = record_hotkey
        self.settings_hotkey = settings_hotkey
        self.on_record_press = on_record_press
        self.on_record_release = on_record_release
        self.on_settings_press = on_settings_press

        self._listener: pynput_keyboard.Listener | None = None
        self._record_down = False
        self._settings_down = False
        self._events_count = 0

    @property
    def events_count(self) -> int:
        return self._events_count

    def _match(self, key, target: ParsedHotkey) -> bool:  # noqa: ANN001
        if target.is_special:
            if target.key_name.startswith("f") and target.key_name[1:].isdigit():
                expected = getattr(pynput_keyboard.Key, target.key_name)
                return key == expected
            if target.key_name == "esc":
                return key == pynput_keyboard.Key.esc
            if target.key_name == "enter":
                return key == pynput_keyboard.Key.enter
            if target.key_name == "tab":
                return key == pynput_keyboard.Key.tab
            if target.key_name == "space":
                return key == pynput_keyboard.Key.space
            return False

        return isinstance(key, pynput_keyboard.KeyCode) and (key.char or "").lower() == target.key_name

    def _on_press(self, key) -> None:  # noqa: ANN001
        self._events_count += 1
        logging.info("key pressed: %s", key)

        if self._match(key, self.record_hotkey):
            logging.info("record hotkey matched on press")
            if not self._record_down:
                self._record_down = True
                self.on_record_press()
            return

        if self._match(key, self.settings_hotkey):
            logging.info("settings hotkey matched on press")
            if not self._settings_down:
                self._settings_down = True
                self.on_settings_press()

    def _on_release(self, key) -> None:  # noqa: ANN001
        self._events_count += 1
        logging.info("key released: %s", key)

        if self._match(key, self.record_hotkey):
            logging.info("record hotkey matched on release")
            if self._record_down:
                self._record_down = False
                self.on_record_release()
            return

        if self._match(key, self.settings_hotkey):
            self._settings_down = False

    def start(self) -> None:
        self._listener = pynput_keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._listener.start()
        logging.info("Pynput listener started")

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()
            self._listener = None


class KeyboardHotkeyListener(_BaseHotkeyListener):
    def __init__(
        self,
        record_hotkey: ParsedHotkey,
        settings_hotkey: ParsedHotkey,
        on_record_press: Callable[[], None],
        on_record_release: Callable[[], None],
        on_settings_press: Callable[[], None],
    ) -> None:
        if not HAS_KEYBOARD:
            raise RuntimeError("keyboard is not installed")

        self.record_hotkey = record_hotkey
        self.settings_hotkey = settings_hotkey
        self.on_record_press = on_record_press
        self.on_record_release = on_record_release
        self.on_settings_press = on_settings_press

        self._record_down = False
        self._settings_down = False
        self._events_count = 0
        self._hook = None

    @property
    def events_count(self) -> int:
        return self._events_count

    def _match(self, key_name: str, target: ParsedHotkey) -> bool:
        return (key_name or "").lower() == target.key_name

    def _handle(self, event) -> None:  # noqa: ANN001
        self._events_count += 1
        key_name = (event.name or "").lower()

        if event.event_type == "down":
            logging.info("key pressed: %s", key_name)
            if self._match(key_name, self.record_hotkey):
                logging.info("record hotkey matched on press")
                if not self._record_down:
                    self._record_down = True
                    self.on_record_press()
                return
            if self._match(key_name, self.settings_hotkey):
                logging.info("settings hotkey matched on press")
                if not self._settings_down:
                    self._settings_down = True
                    self.on_settings_press()

        if event.event_type == "up":
            logging.info("key released: %s", key_name)
            if self._match(key_name, self.record_hotkey):
                logging.info("record hotkey matched on release")
                if self._record_down:
                    self._record_down = False
                    self.on_record_release()
                return
            if self._match(key_name, self.settings_hotkey):
                self._settings_down = False

    def start(self) -> None:
        self._hook = keyboard_lib.hook(self._handle)
        logging.warning("Keyboard listener started (may require admin privileges on Windows)")

    def stop(self) -> None:
        if self._hook is not None:
            keyboard_lib.unhook(self._hook)
            self._hook = None


class HotkeyManager:
    def __init__(
        self,
        record_hotkey: str,
        settings_hotkey: str,
        on_record_press: Callable[[], None],
        on_record_release: Callable[[], None],
        on_settings_press: Callable[[], None],
    ) -> None:
        self.record_hotkey = parse_hotkey_string(record_hotkey, default="f8")
        self.settings_hotkey = parse_hotkey_string(settings_hotkey, default="f10")

        if self.record_hotkey.normalized == self.settings_hotkey.normalized:
            raise ValueError("record hotkey and settings hotkey cannot be identical")

        self.on_record_press = on_record_press
        self.on_record_release = on_record_release
        self.on_settings_press = on_settings_press

        self._impl: _BaseHotkeyListener | None = None
        self._fallback_timer: threading.Timer | None = None

    def _build_pynput(self) -> PynputHotkeyListener:
        return PynputHotkeyListener(
            record_hotkey=self.record_hotkey,
            settings_hotkey=self.settings_hotkey,
            on_record_press=self.on_record_press,
            on_record_release=self.on_record_release,
            on_settings_press=self.on_settings_press,
        )

    def _build_keyboard(self) -> KeyboardHotkeyListener:
        return KeyboardHotkeyListener(
            record_hotkey=self.record_hotkey,
            settings_hotkey=self.settings_hotkey,
            on_record_press=self.on_record_press,
            on_record_release=self.on_record_release,
            on_settings_press=self.on_settings_press,
        )

    def _switch_to_keyboard_fallback(self, reason: str) -> None:
        if isinstance(self._impl, KeyboardHotkeyListener):
            return

        logging.warning("Switching to keyboard fallback: %s", reason)
        if self._impl is not None:
            self._impl.stop()

        self._impl = self._build_keyboard()
        self._impl.start()

    def _start_fallback_watchdog(self) -> None:
        def _check() -> None:
            if isinstance(self._impl, PynputHotkeyListener) and self._impl.events_count == 0:
                self._switch_to_keyboard_fallback("No key events received in first 5 seconds")

        self._fallback_timer = threading.Timer(5.0, _check)
        self._fallback_timer.daemon = True
        self._fallback_timer.start()

    def start(self) -> None:
        try:
            self._impl = self._build_pynput()
            self._impl.start()
            logging.info(
                "Hotkey listener started with pynput: record=%s settings=%s",
                self.record_hotkey.normalized,
                self.settings_hotkey.normalized,
            )
            self._start_fallback_watchdog()
            return
        except Exception:
            logging.exception("Failed to start pynput listener")

        self._switch_to_keyboard_fallback("pynput init failure")

    def stop(self) -> None:
        if self._fallback_timer is not None:
            self._fallback_timer.cancel()
            self._fallback_timer = None

        if self._impl is not None:
            self._impl.stop()
            self._impl = None

    def reload(self, record_hotkey: str, settings_hotkey: str) -> None:
        self.stop()
        self.record_hotkey = parse_hotkey_string(record_hotkey, default="f8")
        self.settings_hotkey = parse_hotkey_string(settings_hotkey, default="f10")
        if self.record_hotkey.normalized == self.settings_hotkey.normalized:
            raise ValueError("record hotkey and settings hotkey cannot be identical")
        self.start()
        logging.info("Hotkeys reloaded")
