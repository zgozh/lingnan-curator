"""文创 Agent 单测：文案 JSON + 实物化渲染接入（渲染失败降级纯文本）。"""
import json

import pytest

from app.agents import creator


HIT = creator._Hit(type("H", (), {
    "photo_id": "p1", "title": "Canton 1850.jpg", "year": "1850",
    "location": "广州", "caption": "老街道"}))

RAW = json.dumps({"title": "百年骑楼", "body": "见字如面。"}, ensure_ascii=False)


def _patch_base(monkeypatch, raw=RAW):
    monkeypatch.setattr(creator, "_hit", lambda pid, settings=None: HIT)
    monkeypatch.setattr(creator.lc, "chat",
                        lambda *a, **k: raw)


def test_create_invalid_type_raises(monkeypatch):
    _patch_base(monkeypatch)
    with pytest.raises(ValueError):
        creator.create("p1", "banner")


def test_create_missing_hit_raises(monkeypatch):
    monkeypatch.setattr(creator, "_hit", lambda pid, settings=None: None)
    with pytest.raises(LookupError):
        creator.create("p1", "postcard")


def test_create_postcard_includes_artifact_urls(monkeypatch):
    _patch_base(monkeypatch)
    monkeypatch.setattr(
        creator, "_render_artifact",
        lambda *a, **k: {"front": "/media/p1/postcard-front.png",
                         "back": "/media/p1/postcard-back.png"})
    out = creator.create("p1", "postcard")
    assert out["copy"] == {"title": "百年骑楼", "body": "见字如面。"}
    assert out["artifact"]["front"].endswith("postcard-front.png")


def test_create_render_failure_degrades_to_text_only(monkeypatch):
    """渲染失败不抛、不带 artifact 键——API 契约保持向后兼容。"""
    _patch_base(monkeypatch)
    monkeypatch.setattr(creator, "_render_artifact", lambda *a, **k: None)
    out = creator.create("p1", "slogan")
    assert out["copy"]["body"] == "见字如面。"
    assert "artifact" not in out


def test_pick_bg_prefers_colorized(tmp_path, monkeypatch):
    from app.infra.artifact import pick_background

    d = tmp_path / "p1"
    d.mkdir()
    assert pick_background(d) is None            # 无图 → None
    (d / "restored.jpg").write_bytes(b"x")
    assert pick_background(d).name == "restored.jpg"
    (d / "colorized.jpg").write_bytes(b"x")
    assert pick_background(d).name == "colorized.jpg"   # 上色优先
    (d / "enhanced.jpg").write_bytes(b"x")
    assert pick_background(d).name == "enhanced.jpg"    # 增强图最优先
