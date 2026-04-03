from __future__ import annotations

import logging
import os
from pathlib import Path

from openai import APITimeoutError, OpenAI, OpenAIError

from speech_to_text import speech_to_text as transcribe_wav


class GPTClient:
    def __init__(
        self,
        model: str = "gpt-4.1-mini",
        system_prompt: str | None = None,
        timeout: float = 20.0,
    ) -> None:
        self.model = model
        self.system_prompt = system_prompt or "You are a concise and helpful assistant."
        self.timeout = timeout

        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key:
            logging.warning("OPENAI_API_KEY is not set.")
            self._client = None
            return

        self._client = OpenAI(api_key=api_key, timeout=timeout)

    def speech_to_text(self, audio_path: str | Path) -> str:
        """Stable speech-to-text interface.

        Delegates to `speech_to_text.py` so backend can be replaced independently.
        """
        return transcribe_wav(audio_path)

    def ask_gpt(self, text: str) -> str:
        """Call OpenAI Responses API and return plain text output."""
        user_text = (text or "").strip()
        if not user_text:
            return ""

        if self._client is None:
            return "[ask_gpt error] Missing OPENAI_API_KEY"

        try:
            resp = self._client.responses.create(
                model=self.model,
                input=[
                    {"role": "system", "content": self.system_prompt},
                    {"role": "user", "content": user_text},
                ],
            )

            output_text = (getattr(resp, "output_text", "") or "").strip()
            if not output_text:
                logging.warning("ask_gpt returned empty output_text.")
                return "[ask_gpt empty reply]"
            return output_text

        except APITimeoutError:
            logging.exception("ask_gpt timeout after %.1fs", self.timeout)
            return "[ask_gpt timeout]"
        except OpenAIError:
            logging.exception("ask_gpt OpenAI request failed.")
            return "[ask_gpt request failed]"
        except Exception:
            logging.exception("ask_gpt unexpected error.")
            return "[ask_gpt unexpected error]"
