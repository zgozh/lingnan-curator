"""run_story_chain 编排器单测：happy path / 幂等缓存 / 降级兜底 / 审稿回炉。

deps 注入 seam（_DefaultDeps 可用测试替身替换）+ tmp_path（conftest）保底，
全程不触网、不依赖真实外部服务。
"""
from pathlib import Path

from app.config import Settings
from app.narrator.story import run_story_chain
from app.narrator.types import Insight, Narration, NarrationLine, ReviewResult, Story

STORY_GOOD = "一个关于广州骑楼的老故事。" * 20  # >80 字且无禁用词


class Deps:
    """Brief 给定 happy-path 替身；不写 wav（幂等测试另有 tts 落盘代理）。"""

    @staticmethod
    def insight(*a, **k):
        return Insight(scene="骑楼街", source="vlm", degraded=False)

    @staticmethod
    def write_story(*a, **k):
        return Story(text=STORY_GOOD, source="llm")

    @staticmethod
    def write_narration(*a, **k):
        return Narration(lines=[NarrationLine(text="呢句系粤语旁白。", emotion="怀念")] * 6)

    @staticmethod
    def review(*a, **k):
        return ReviewResult(score=90)

    @staticmethod
    def tts(*a, **k):
        return True


def _counting(impl, tts_writes_wav=False):
    """包一层计数代理：记录各方法调用次数；可选让 tts 真正落盘 wav（幂等缓存用）。"""
    calls = {"insight": 0, "write_story": 0, "write_narration": 0, "review": 0, "tts": 0}

    class Proxy:
        @staticmethod
        def insight(*a, **k):
            calls["insight"] += 1
            return impl.insight(*a, **k)

        @staticmethod
        def write_story(*a, **k):
            calls["write_story"] += 1
            return impl.write_story(*a, **k)

        @staticmethod
        def write_narration(*a, **k):
            calls["write_narration"] += 1
            return impl.write_narration(*a, **k)

        @staticmethod
        def review(*a, **k):
            calls["review"] += 1
            return impl.review(*a, **k)

        @staticmethod
        def tts(*a, **k):
            calls["tts"] += 1
            if tts_writes_wav and a:
                Path(a[-1]).write_bytes(b"")  # 模拟 TTS 产物落盘
            return impl.tts(*a, **k)

    return Proxy, calls


def test_run_story_chain_happy(tmp_path):
    res = run_story_chain("sample_a", settings=None, out_root=tmp_path, deps=Deps)
    assert res["story"] != ""
    assert res["narration"] != ""
    assert res["audio"] is True
    assert res["degraded"] is False
    assert res["source"] == "llm"
    # 产物落盘
    assert (tmp_path / "sample_a" / "story.json").exists()
    assert (tmp_path / "sample_a" / "narration.json").exists()


def test_run_story_chain_idempotent_cache(tmp_path):
    """三次调用同一 photo_id：二次命中缓存不重跑；force=True 强制重算。"""
    proxy, calls = _counting(Deps, tts_writes_wav=True)
    first = run_story_chain("sample_b", settings=None, out_root=tmp_path, deps=proxy)
    assert first["audio"] is True
    assert calls["insight"] == 1 and calls["tts"] == 1

    second = run_story_chain("sample_b", settings=None, out_root=tmp_path, deps=proxy)
    assert second["story"] == first["story"]
    assert second["narration"] == first["narration"]
    assert second["audio"] is True
    # 幂等：二次调用完全没碰 deps
    assert calls == {"insight": 1, "write_story": 1, "write_narration": 1, "review": 1, "tts": 1}

    third = run_story_chain("sample_b", settings=None, force=True,
                            out_root=tmp_path, deps=proxy)
    assert calls["insight"] == 2  # force 绕过缓存，整链重跑


class DegradedStoryDeps:
    """write_story 返回 degraded → 应落入 fallback_docent 兜底。"""

    @staticmethod
    def insight(*a, **k):
        return Insight(scene="骑楼街", source="vlm", degraded=False)

    @staticmethod
    def write_story(*a, **k):
        return Story(text="短到不合格。", source="llm", degraded=True)

    @staticmethod
    def write_narration(*a, **k):
        return Narration(lines=[NarrationLine(text="呢句系粤语旁白。", emotion="怀念")] * 6)

    @staticmethod
    def review(*a, **k):
        return ReviewResult(score=90)

    @staticmethod
    def tts(*a, **k):
        return True


def test_run_story_chain_fallback_on_degraded_story(tmp_path):
    res = run_story_chain("sample_c", settings=None, out_root=tmp_path, deps=DegradedStoryDeps)
    assert res["source"] == "fallback_docent"
    assert res["degraded"] is True
    assert "岭南" in res["story"]  # 兜底稿来自元数据
    # 兜底稿也照常产出旁白与音频
    assert res["narration"] != ""
    assert res["audio"] is True


class RetryDeps:
    """审稿 60 分 + 首稿 detox 不过 → 编排器应回炉重写一次。"""

    story_calls = 0
    narration_calls = 0

    @staticmethod
    def insight(*a, **k):
        return Insight(scene="骑楼街", source="vlm", degraded=False)

    @staticmethod
    def write_story(*a, **k):
        RetryDeps.story_calls += 1
        if RetryDeps.story_calls == 1:
            return Story(text="短句不合格。", source="llm")  # 过短 → detox 不过
        return Story(text=STORY_GOOD, source="llm")

    @staticmethod
    def write_narration(*a, **k):
        RetryDeps.narration_calls += 1
        return Narration(lines=[NarrationLine(text="呢句系粤语旁白。", emotion="怀念")] * 6)

    @staticmethod
    def review(*a, **k):
        return ReviewResult(score=60, issues=["事实不符"], suggestion="重写")

    @staticmethod
    def tts(*a, **k):
        return True


def test_run_story_chain_review_retry_regenerates_once(tmp_path):
    st = Settings(max_story_retry=1)  # 显式配置，脱离 .env 影响
    RetryDeps.story_calls = 0
    RetryDeps.narration_calls = 0
    res = run_story_chain("sample_d", settings=st, out_root=tmp_path, deps=RetryDeps)
    assert RetryDeps.story_calls == 2       # 首稿 + 回炉一次
    assert RetryDeps.narration_calls == 2   # 回炉后旁白重写
    assert res["story"] == STORY_GOOD       # 回炉稿胜出
    assert res["source"] == "llm"
    assert res["degraded"] is True          # 审稿低分已标记降级
    assert res["audio"] is True