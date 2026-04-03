from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from llm.base import LLMProvider
from router import choose_model_by_complexity
from utils.text_rules import is_insufficient_answer

if TYPE_CHECKING:
    from config import AppConfig


def create_provider(config: "AppConfig", model: str | None = None) -> LLMProvider:
    selected_model = model or config.balanced_model

    if config.llm_provider == "openai_compatible":
        from llm.compatible_provider import OpenAICompatibleProvider

        return OpenAICompatibleProvider(
            model=selected_model,
            api_key=config.api_key,
            base_url=config.base_url,
            timeout=config.openai_timeout,
        )

    from llm.openai_provider import OpenAIResponsesProvider

    return OpenAIResponsesProvider(
        model=selected_model,
        api_key=config.api_key,
        base_url=config.base_url,
        timeout=config.openai_timeout,
    )


def ask_with_fallback(
    user_text: str,
    complexity: str,
    config: "AppConfig",
    history: list[dict] | None = None,
    system_prompt: str = "",
) -> tuple[str, str, bool]:
    primary_model = choose_model_by_complexity(complexity)
    provider = create_provider(config, model=primary_model)

    response = provider.ask(user_text=user_text, system_prompt=system_prompt, history=history)
    fallback_triggered = False

    if complexity == "simple" and is_insufficient_answer(response):
        fallback_triggered = True
        logging.info("Fallback triggered: simple -> balanced")
        fallback_provider = create_provider(config, model=config.balanced_model)
        upgraded = fallback_provider.ask(user_text=user_text, system_prompt=system_prompt, history=history)
        if upgraded.strip():
            return upgraded, config.balanced_model, True

    return response, primary_model, fallback_triggered
