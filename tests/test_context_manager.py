from context_manager import trim_history


def test_trim_history_limits() -> None:
    history = [
        {"role": "user", "content": "u1"},
        {"role": "assistant", "content": "a1"},
        {"role": "user", "content": "u2"},
        {"role": "assistant", "content": "a2"},
        {"role": "user", "content": "u3"},
        {"role": "assistant", "content": "a3"},
    ]
    trimmed = trim_history(history, max_turns=4, max_chars=6)
    assert len(trimmed) <= 4
    assert sum(len(x["content"]) for x in trimmed) <= 6
