from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from config import AppConfig

SETTINGS_PATH = Path("settings.json")


def _default_settings() -> dict[str, Any]:
    cfg = AppConfig()
    data = cfg.__dict__.copy()
    data.pop("extra", None)
    return data


def load_settings(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    defaults = _default_settings()
    if not path.exists():
        return defaults

    try:
        loaded = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(loaded, dict):
            logging.warning("settings.json is not an object, fallback to defaults")
            return defaults
        defaults.update(loaded)
        return defaults
    except Exception:
        logging.exception("Failed to load settings, fallback to defaults")
        return defaults


def save_settings(data: dict[str, Any], path: Path = SETTINGS_PATH) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    logging.info("Settings saved")


def reload_settings(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    return load_settings(path)
