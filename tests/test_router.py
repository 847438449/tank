from router import quick_rule_classify


def test_simple_word_meaning() -> None:
    assert quick_rule_classify("这个词是什么意思") == "simple"


def test_simple_translate() -> None:
    assert quick_rule_classify("帮我把这句话翻译成日语") == "simple"


def test_complex_architecture() -> None:
    assert quick_rule_classify("帮我设计一个带热键录音、语音转文字、悬浮窗显示的桌面架构") == "complex"


def test_complex_debug() -> None:
    assert quick_rule_classify("为什么这个程序会报错，应该如何排查") == "complex"
