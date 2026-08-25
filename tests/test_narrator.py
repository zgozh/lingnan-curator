"""T3 RED：narrator——photo_id→馆藏著录→粤语讲解词→TTS 音频（全 mock 封闭）。"""
import json

import app.agents.narrator as nr


class Hit:
    def __init__(self, pid="sample_a"):
        self.photo_id = pid
        self.title = "骑楼街景"
        self.year = "1930"
        self.location = "广州"
        self.caption = "1920年代广州骑楼，柱廊行人如鲫"


class FakeTTS:
    def __init__(self, ok=True):
        self.ok = ok
        self.calls = []

    def synthesize(self, text, voice, out_path):
        self.calls.append((text, voice, str(out_path)))
        if self.ok:
            p = __import__("pathlib").Path(out_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(b"RIFF")
        return self.ok


_MISSING = object()  # 显式“无馆藏”哨兵


def _patch_common(monkeypatch, hit=_MISSING,
                  llm_text='{"script": "各位观众，呢张相影住旧时广州嘅骑楼。"}',
                  tts_ok=True):
    calls = {}

    resolved = Hit() if hit is _MISSING else hit
    monkeypatch.setattr(nr, "_hit", lambda pid, settings=None: resolved)
    monkeypatch.setattr(
        nr.lc, "chat",
        lambda messages, **kw: (calls.update(messages=messages), llm_text)[1])
    fake = FakeTTS(tts_ok)
    monkeypatch.setattr(nr, "_tts", lambda settings=None: fake)
    return calls, fake


def test_script_generated_in_cantonese(monkeypatch):
    calls, _ = _patch_common(monkeypatch)
    out = nr.write_script("sample_a")
    assert calls.get("messages"), "LLM 未被调用"
    joined = json.dumps(calls["messages"], ensure_ascii=False)
    assert "骑楼" in joined
    assert out.startswith("各位观众")


def test_missing_photo_raises_lookuperror(monkeypatch):
    import pytest

    _patch_common(monkeypatch, hit=None)  # 显式无馆藏
    with pytest.raises(LookupError):
        nr.write_script("ghost")


def test_narrate_produces_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(nr, "_out_dir", lambda pid: tmp_path / pid)
    calls, fake = _patch_common(monkeypatch)
    result = nr.narrate("sample_a")
    assert result["audio"] is True and result["degraded"] is False
    assert fake.calls and fake.calls[0][1]  # voice 来自配置


def test_tts_failure_marks_degraded(monkeypatch, tmp_path):
    monkeypatch.setattr(nr, "_out_dir", lambda pid: tmp_path / pid)
    _, fake = _patch_common(monkeypatch, tts_ok=False)
    result = nr.narrate("sample_a")
    assert result["audio"] is False and result["degraded"] is True
