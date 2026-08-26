"""Task 2：叙事链结构化类型（app.narrator.types）默认值。"""
from app.narrator.types import (
    Character,
    Insight,
    Narration,
    NarrationLine,
    ReviewResult,
    Story,
)


def test_character_defaults():
    c = Character()
    assert c.who == ""
    assert c.clothing == ""
    assert c.age_hint == ""


def test_insight_defaults():
    i = Insight()
    assert i.scene == ""
    assert i.visibles == []
    assert i.characters == []
    assert i.era_evidence == []
    assert i.maybe_place == "不确定"
    assert i.mood == ""
    assert i.confident_words == ""
    assert i.source == "vlm"
    assert i.degraded is False


def test_insight_default_factories_are_independent():
    a, b = Insight(), Insight()
    a.visibles.append("骑楼")
    a.characters.append(Character(who="报童"))
    assert b.visibles == []
    assert b.characters == []


def test_story_defaults():
    s = Story()
    assert s.text == ""
    assert s.source == "llm"
    assert s.degraded is False


def test_narration_line_defaults():
    line = NarrationLine()
    assert line.text == ""
    assert line.emotion == "平静"


def test_narration_defaults():
    n = Narration()
    assert n.lines == []


def test_narration_holds_lines():
    n = Narration(lines=[NarrationLine(text="晨光洒落骑楼", emotion="怀念")])
    assert n.lines[0].emotion == "怀念"


def test_review_result_defaults():
    r = ReviewResult()
    assert r.score == 0
    assert r.issues == []
    assert r.suggestion == ""