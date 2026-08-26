"""叙事链提示词集中模块的约束测试（供后续 Task 的 Agent 实现依赖这些关键词）。"""

from app.narrator import prompts as p

PROMPT_NAMES = (
    "INSIGHT_SYSTEM",
    "STORY_SYSTEM",
    "NARRATION_SYSTEM",
    "REVIEW_SYSTEM",
    "FALLBACK_SINGLE_SYSTEM",
)


def test_story_system_has_anti_ai_clause():
    assert "严禁" in p.STORY_SYSTEM
    assert "AI 腔" in p.STORY_SYSTEM or "套话" in p.STORY_SYSTEM


def test_story_system_forbids_hallucination():
    assert "不编造" in p.STORY_SYSTEM


def test_story_system_has_length_and_hook_requirements():
    assert "300-400 字" in p.STORY_SYSTEM
    assert "开头一句抓人" in p.STORY_SYSTEM
    assert "留余韵" in p.STORY_SYSTEM


def test_narration_system_has_emotion_enum():
    assert "怀念" in p.NARRATION_SYSTEM


def test_narration_system_has_sentence_and_json_requirements():
    assert "5-7 句" in p.NARRATION_SYSTEM
    assert "10-20 字" in p.NARRATION_SYSTEM
    assert "只输出 JSON" in p.NARRATION_SYSTEM


def test_review_system_returns_score():
    assert "score" in p.REVIEW_SYSTEM or "0-100" in p.REVIEW_SYSTEM


def test_review_system_has_dimensions():
    assert "事实一致性" in p.REVIEW_SYSTEM
    assert "AI 腔" in p.REVIEW_SYSTEM


def test_insight_system_only_output_json():
    assert "只输出 JSON" in p.INSIGHT_SYSTEM


def test_insight_system_has_place_and_words_keys():
    assert "maybe_place" in p.INSIGHT_SYSTEM
    assert "confident_words" in p.INSIGHT_SYSTEM


def test_fallback_single_has_two_blocks():
    assert "【故事】" in p.FALLBACK_SINGLE_SYSTEM
    assert "【旁白】" in p.FALLBACK_SINGLE_SYSTEM


def test_all_prompts_are_str():
    for name in PROMPT_NAMES:
        assert isinstance(getattr(p, name), str)