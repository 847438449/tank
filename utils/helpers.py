from __future__ import annotations


def normalize_level(level: str, default: str = "medium") -> str:
    candidate = (level or "").strip().lower()
    if candidate in {"simple", "medium", "complex"}:
        return candidate
    return default
