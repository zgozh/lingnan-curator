"""T10：按句合成（正确 WAV 拼接）+ Edge-TTS Provider 候选。"""
import io
import sys
import wave

import pytest

import app.infra.tts as tts
from app.config import Settings


def _make_wav(nframes: int = 1) -> bytes:
    """用 wave 构造一个最小 mono/16bit WAV 字节串（默认 1 帧）。"""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(22050)
        w.writeframes(b"\x00\x00" * nframes)  # 每帧 2 字节（16bit mono）
    return buf.getvalue()


class _FakeWavSynth:
    """._call(text) 返回 1 帧最小 WAV；两行拼起来应为 2 帧。"""

    def __init__(self, model, voice, audio_format):
        self.model, self.voice, self.audio_format = model, voice, audio_format

    def call(self, text):
        return _make_wav(1)


def test_synthesize_lines_empty_false():
    assert tts.synthesize_lines([], "x.wav", settings=None) is False


def test_synthesize_lines_concatenates(monkeypatch, tmp_path):
    monkeypatch.setattr(tts, "_new_synthesizer",
                        lambda model, voice, fmt: _FakeWavSynth(model, voice, fmt))
    out = tmp_path / "nar.wav"
    lines = [
        {"text": "第一句", "emotion": "怀念"},
        {"text": "第二句", "emotion": "平静"},
    ]
    assert tts.synthesize_lines(lines, out, settings=None) is True
    assert out.exists()
    with wave.open(str(out), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == 22050
        assert w.getsampwidth() == 2
        assert w.getnframes() == 2  # 两段各 1 帧，正确拼接而非裸字节拼接


def test_get_tts_edge_when_configured():
    s = Settings(tts_provider="edge")
    assert isinstance(tts.get_tts(s), tts.EdgeTTSCosyvoice)


def test_get_tts_dashscope_by_default():
    s = Settings(tts_provider="dashscope")
    assert isinstance(tts.get_tts(s), tts.DashScopeCosyvoice)


def test_edge_tts_returns_false_without_module(monkeypatch, tmp_path):
    # 让 import edge_tts 失败（`None in sys.modules` → ImportError），必须返回 False，
    # 且不炸 import、不抛异常。
    monkeypatch.setitem(sys.modules, "edge_tts", None)
    out = tmp_path / "e.wav"
    assert tts.EdgeTTSCosyvoice().synthesize("你好", "v", out) is False
