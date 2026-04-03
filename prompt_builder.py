from __future__ import annotations


def build_classifier_prompt(text: str) -> str:
    return f"Classify to one label only: simple/medium/complex. Text: {text}"


def build_answer_prompt(text: str, complexity: str) -> str:
    if complexity == "simple":
        return "你是桌面助手。请用简洁中文回答（1-3句），直接给结论。"
    if complexity == "complex":
        return "你是桌面助手。请结构化回答，先结论再步骤，尽量清晰但避免冗长。"
    return "你是桌面助手。请给出清楚、简洁、可执行的回答。"


def build_summary_prompt(history: list[dict]) -> str:
    blocks = []
    for item in history:
        role = item.get("role", "user")
        content = item.get("content", "")
        blocks.append(f"{role}: {content}")
    joined = "\n".join(blocks)
    return "请将以下历史对话压缩为不超过120字的关键上下文，仅保留目标、约束和未解决问题：\n" + joined
