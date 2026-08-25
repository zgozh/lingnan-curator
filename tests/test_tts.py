"""T1 RED：TTS 基座——DashScope Cosyvoice 适配，失败一律 False。"""
import pytest

import app.infra.tts as tts


class FakeSynth:
    instances = []

    def __init__(self, model, voice, audio_format):
        self.model, self.voice = model, voice
        FakeSynth.instances.append(self)

    def call(self, text):
        if "空" in text:
            return b""
        return b"RIFF-fake-audio"


@pytest.fixture
def fake_sdk(monkeypatch):
    FakeSynth.instances.clear()
    monkeypatch.setattr(tts, "_new_synthesizer",
                        lambda model, voice, fmt: FakeSynth(model, voice, fmt))
    return FakeSynth


def _prov():
    return tts.DashScopeCosyvoice()


def test_synthesize_writes_wav(fake_sdk, tmp_path):
    out = tmp_path / "n.wav"
    ok = _prov().synthesize("你好，欢迎来到展馆", "longjiaxin_v3", out)
    assert ok is True and out.read_bytes().startswith(b"RIFF")
    inst = fake_sdk.instances[-1]
    assert inst.voice == "longjiaxin_v3"
    assert "cosyvoice" in inst.model


def test_synthesize_empty_text_returns_false(fake_sdk, tmp_path):
    assert _prov().synthesize("   ", "v", tmp_path / "a.wav") is False


def test_synthesize_blank_audio_returns_false(fake_sdk, tmp_path):
    assert _prov().synthesize("空文本", "v", tmp_path / "a.wav") is False


def test_synthesize_exception_returns_false(monkeypatch, tmp_path):
    def boom(model, voice, fmt):
        raise RuntimeError("key 无效")

    monkeypatch.setattr(tts, "_new_synthesizer", boom)
    assert _prov().synthesize("x", "v", tmp_path / "a.wav") is False


def test_missing_key_short_circuits(monkeypatch, tmp_path):
    import dataclasses

    from app.config import Settings

    s = dataclasses.replace(Settings.load(), dashscope_api_key="")
    called = []
    monkeypatch.setattr(tts, "_new_synthesizer",
                        lambda *a: called.append(1))
    assert tts.DashScopeCosyvoice(s).synthesize("x", "v", tmp_path / "a.wav") is False
    assert not called
