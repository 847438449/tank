from __future__ import annotations

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    @abstractmethod
    def ask(
        self,
        user_text: str,
        system_prompt: str = "",
        history: list | None = None,
        stream: bool = False,
    ) -> str:
        raise NotImplementedError
