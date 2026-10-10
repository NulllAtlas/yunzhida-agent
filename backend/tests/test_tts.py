"""语音对话（TTS）的纯函数单测：不联网，只测朗读文本的清洗。"""
from app.services.tts import _strip_markdown, synthesize


def test_strip_markdown_removes_links_and_symbols():
    raw = "## **研判结果**\n详见 [文档](https://example.com/a) 与 *要点*。"
    clean = _strip_markdown(raw)
    assert "#" not in clean and "*" not in clean
    assert "example.com" not in clean
    assert "研判结果" in clean and "要点" in clean


def test_strip_markdown_keeps_plain_text():
    assert _strip_markdown("别担心，先确认安全。") == "别担心，先确认安全。"


def test_synthesize_rejects_empty_text():
    assert synthesize("") is None
    assert synthesize("###") is None  # 清洗后为空也不合成
