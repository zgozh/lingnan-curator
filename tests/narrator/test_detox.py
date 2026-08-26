from app.narrator.types import NarrationLine
from app.narrator import detox as d

def test_scan_hits_banned():
    assert d.scan_ai_smell("在这个世界上，岁月如梭。") != []

def test_scan_empty_on_clean():
    assert d.scan_ai_smell("骑楼下面，老广州嘅茶楼。") == []

def test_validate_story_rejects_short_or_banned():
    assert d.validate_story("太短") is False
    assert d.validate_story("是个好故事" * 20 + "岁月的长河承载了记忆") is False

def test_validate_narration_rejects():
    good = [NarrationLine(text="嗰阵广州好热闹。", emotion="怀念")]
    assert d.validate_narration(good) is False
    bad_emo = [NarrationLine(text="x" * 12, emotion="生气") for _ in range(6)]
    assert d.validate_narration(bad_emo) is False
    good6 = [NarrationLine(text="呢句刚好十二个字啊。", emotion="怀念") for _ in range(6)]
    assert d.validate_narration(good6) is True