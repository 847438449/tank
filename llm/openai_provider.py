from __future__ import annotations

import logging
import os

from openai import APITimeoutError, OpenAI, OpenAIError

from llm.base import LLMProvider


class OpenAIResponsesProvider(LLMProvider):
    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        base_url: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.model = model
        self.timeout = timeout

        final_key = (api_key or os.getenv("OPENAI_API_KEY", "")).strip()
        if not final_key:
            raise ValueError("OPENAI_API_KEY is missing")

        client_kwargs: dict = {"api_key": final_key, "timeout": timeout}
        if base_url:
            client_kwargs["base_url"] = base_url
        self.client = OpenAI(**client_kwargs)

    def ask(
        self,
        user_text: str,
        system_prompt: str = "",
        history: list | None = None,
        stream: bool = False,
    ) -> str:
        if not user_text.strip():
            return ""

        input_items: list[dict] = []
        if system_prompt:
            input_items.append({"role": "system", "content": system_prompt})

        for message in history or []:
            role = message.get("role", "user")
            content = (message.get("content", "") or "").strip()
            if content:
                input_items.append({"role": role, "content": content})

        input_items.append({"role": "user", "content": user_text})

        try:
            response = self.client.responses.create(
                model=self.model,
                input=input_items,
            )
            output = (getattr(response, "output_text", "") or "").strip()
            return output
        except APITimeoutError:
            logging.exception("OpenAIResponsesProvider timeout model=%s", self.model)
            return "[llm timeout]"
        except OpenAIError:
            logging.exception("OpenAIResponsesProvider request failed model=%s", self.model)
            return "[llm request failed]"
        except Exception:
            logging.exception("OpenAIResponsesProvider unexpected error model=%s", self.model)
            return "[llm unexpected error]"
