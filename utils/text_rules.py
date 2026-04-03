from __future__ import annotations

SIMPLE_HINTS = [
    "翻译",
    "怎么说",
    "几点",
    "什么意思",
    "改一句",
    "润色一句",
    "解释一下这个词",
]

COMPLEX_HINTS = [
    "为什么",
    "分析",
    "比较",
    "设计",
    "实现",
    "优化",
    "架构",
    "排查",
    "调试",
    "重构",
    "方案",
    "步骤",
    "原因",
]

WEAK_ANSWER_HINTS = ["无法判断", "信息不足", "我不确定", "不太确定", "无法确定"]


def contains_any(text: str, keywords: list[str]) -> bool:
    lower_text = (text or "").lower()
    return any(word.lower() in lower_text for word in keywords)


def is_insufficient_answer(text: str, min_len: int = 10) -> bool:
    content = (text or "").strip()
    if len(content) < min_len:
        return True
    return contains_any(content, WEAK_ANSWER_HINTS)
