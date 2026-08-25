"""T4 RED：LLM 文本客户端——chat/stream_chat + JSON 防御解析上移。"""
import json

import app.infra.llm_client as lc
from app.utils.json_utils import extract_json


class FakeCompletions:
    def __init__(self, content=None, chunks=()):
        self._content = content
        self._chunks = chunks
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        if self._chunks:
            return iter(self._chunks)
        msg = type("M", (), {"content": self._content})()
        choice = type("C", (), {"message": msg})()
        return type("R", (), {"choices": [choice]})()


def _patch_llm(monkeypatch, completions):
    monkeypatch.setattr(
        lc, "get_llm", lambda settings=None: type("L", (), {"chat": completions})()
    )


def test_extract_json_tolerates_wrapped_text():
    raw = '好的，结果如下：{"a": 1, "b": "x"} 以上。'
    assert extract_json(raw) == {"a": 1, "b": "x"}


def test_extract_json_invalid_returns_none():
    assert extract_json("完全不是 JSON") is None


def test_chat_returns_content(monkeypatch):
    comp = FakeCompletions(content="答案")
    _patch_llm(monkeypatch, comp)
    out = lc.chat([{"role": "user", "content": "问"}], settings=None,
                  client_factory=lambda **kw: type("S", (), {"chat": comp})())
    assert out == "答案"
    assert comp.kwargs["model"]


def test_chat_json_mode_sets_response_format(monkeypatch):
    comp = FakeCompletions(content='{"ok": true}')
    _patch_llm(monkeypatch, comp)
    raw = lc.chat([{"role": "user", "content": "问"}], json_mode=True,
                  client_factory=lambda **kw: type("S", (), {"chat": comp})())
    assert comp.kwargs.get("response_format") == {"type": "json_object"}
    assert extract_json(raw) == {"ok": True}


def test_stream_chat_yields_deltas(monkeypatch):
    chunk = lambda i: type("K", (), {}, )() if False else None
    parts = ["你好", "，", "世界"]

    def make_chunk(text):
        delta = type("D", (), {"content": text})()
        choice = type("C", (), {"delta": delta})()
        return type("K", (), {"choices": [choice]})()

    comp = FakeCompletions(chunks=[make_chunk(p) for p in parts])
    _patch_llm(monkeypatch, comp)
    got = list(lc.stream_chat([{"role": "user", "content": "问"}],
                              client_factory=lambda **kw: type("S", (), {"chat": comp})()))
    assert got == parts
