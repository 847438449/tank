from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CHEAP_MODEL = "gpt-4o-mini"
BALANCED_MODEL = "gpt-5.4-mini"
PREMIUM_MODEL = "gpt-5.4"


@dataclass
class AppConfig:
    hotkey: str = "f8"
    sample_rate: int = 16000
    channels: int = 1
    overlay_width: int = 420
    overlay_height: int = 120
    overlay_offset_x: int = 24
    overlay_offset_y: int = 24
    llm_provider: str = "openai"
    api_key: str = ""
    base_url: str = ""
    classifier_model: str = CHEAP_MODEL
    summary_model: str = CHEAP_MODEL
    cheap_model: str = CHEAP_MODEL
    balanced_model: str = BALANCED_MODEL
    premium_model: str = PREMIUM_MODEL
    openai_timeout: float = 20.0
    openai_system_prompt: str = "你是简洁且可靠的桌面助手。"
    max_history_turns: int = 6
    max_history_chars: int = 2200
    log_level: str = "INFO"
    extra: dict[str, Any] = field(default_factory=dict)


DEFAULT_CONFIG_PATH = Path("settings.json")
LEGACY_CONFIG_PATH = Path("config.json")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_config(path: str | Path = DEFAULT_CONFIG_PATH) -> AppConfig:
    cfg_path = Path(path)
    raw: dict[str, Any] = {}

    if cfg_path.exists():
        try:
            raw = _read_json(cfg_path)
        except Exception:
            logging.exception("Failed to parse config file: %s", cfg_path)
    elif LEGACY_CONFIG_PATH.exists():
        try:
            raw = _read_json(LEGACY_CONFIG_PATH)
            logging.warning("settings.json not found, loaded legacy config.json")
        except Exception:
            logging.exception("Failed to parse legacy config file: %s", LEGACY_CONFIG_PATH)
    else:
        logging.warning("No config file found, using defaults")

    known_fields = set(AppConfig.__dataclass_fields__.keys())  # noqa: SLF001
    typed_values = {k: v for k, v in raw.items() if k in known_fields}
    extra = {k: v for k, v in raw.items() if k not in known_fields}

    cfg = AppConfig(**typed_values)
    cfg.extra = extra

    if not cfg.api_key:
        cfg.api_key = os.getenv("OPENAI_API_KEY", "").strip()

    return cfg
