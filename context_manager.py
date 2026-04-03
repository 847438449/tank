from __future__ import annotations

import logging

from llm.base import LLMProvider
from prompt_builder import build_summary_prompt


def trim_history(history: list[dict], max_turns: int, max_chars: int) -> list[dict]:
    if not history:
        return []

    recent = history[-max_turns:]
    output: list[dict] = []
    total_chars = 0

    for item in reversed(recent):
        content = (item.get("content", "") or "")
        new_total = total_chars + len(content)
        if new_total > max_chars and output:
            break
        output.append(item)
        total_chars = new_total

    output.reverse()
    return output


def summarize_history(history: list[dict], provider: LLMProvider) -> str:
    if not history:
        return ""

    try:
        prompt = build_summary_prompt(history)
        summary = provider.ask(
            user_text=prompt,
            system_prompt="你是对话压缩助手。仅输出摘要正文，不要解释。",
        )
        summary_text = (summary or "").strip()
        if not summary_text:
            return ""
        return summary_text
    except Exception:
        logging.exception("summarize_history failed")
        return ""


def build_context_for_request(
    history: list[dict],
    complexity: str,
    provider: LLMProvider | None = None,
) -> list[dict]:
    if not history:
        return []

    if complexity == "simple":
        return trim_history(history, max_turns=2, max_chars=400)

    if complexity == "medium":
        return trim_history(history, max_turns=4, max_chars=1200)

    recent = trim_history(history, max_turns=4, max_chars=1200)
    older = history[:-len(recent)] if recent else history

    if provider and older:
        summary = summarize_history(older, provider)
        if summary:
            logging.info("Context summary generated for complex request")
            return [{"role": "system", "content": f"历史摘要: {summary}"}, *recent]

    logging.info("Context summary skipped or failed, using trimmed history")
    return trim_history(history, max_turns=6, max_chars=1800)
