from dataclasses import dataclass

from llm.factory import ask_with_fallback


@dataclass
class DummyConfig:
    llm_provider: str = "openai"
    api_key: str = "dummy"
    base_url: str = ""
    openai_timeout: float = 20.0
    balanced_model: str = "balanced-model"


def test_placeholder_import() -> None:
    # TODO: 可在后续注入 mock provider 进行端到端 fallback 行为测试。
    cfg = DummyConfig()
    assert cfg.balanced_model == "balanced-model"
    assert ask_with_fallback.__name__ == "ask_with_fallback"
