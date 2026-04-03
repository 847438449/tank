from __future__ import annotations

import logging

from llm.base import LLMProvider
from prompt_builder import build_classifier_prompt
from utils.helpers import normalize_level
from utils.text_rules import COMPLEX_HINTS, SIMPLE_HINTS, contains_any

MODEL_MAPPING = {
    "simple": "gpt-4o-mini",
    "medium": "gpt-5.4-mini",
    "complex": "gpt-5.4",
}


def configure_model_mapping(cheap_model: str, balanced_model: str, premium_model: str) -> None:
    MODEL_MAPPING["simple"] = cheap_model
    MODEL_MAPPING["medium"] = balanced_model
    MODEL_MAPPING["complex"] = premium_model


def quick_rule_classify(text: str) -> str | None:
    clean = (text or "").strip()
    if not clean:
        return "simple"

    if len(clean) <= 20 and not contains_any(clean, COMPLEX_HINTS):
        return "simple"

    if contains_any(clean, SIMPLE_HINTS):
        return "simple"

    if contains_any(clean, COMPLEX_HINTS):
        return "complex"

    return None


def ai_classify(text: str, provider: LLMProvider) -> str:
    prompt = build_classifier_prompt(text)
    raw = provider.ask(user_text=prompt, system_prompt="Return one word: simple/medium/complex.")
    label = normalize_level(raw.split()[0] if raw else "", default="medium")
    if label not in {"simple", "medium", "complex"}:
        return "medium"
    return label


def classify_complexity(text: str, provider: LLMProvider) -> str:
    quick = quick_rule_classify(text)
    if quick in {"simple", "complex"}:
        logging.info("Router decided by quick rules: %s", quick)
        return quick

    try:
        result = ai_classify(text=text, provider=provider)
        logging.info("Router decided by AI classifier: %s", result)
        return result
    except Exception:
        logging.exception("AI classify failed, fallback to medium")
        return "medium"


def choose_model_by_complexity(level: str) -> str:
    normalized = normalize_level(level, default="medium")
    return MODEL_MAPPING[normalized]
