"""T6 RED：策展人(主题→展览JSON) + 文创(photo_id→文案JSON)。"""
import app.agents.curator as cu
import app.agents.creator as cr


class Hit:
    def __init__(self, pid, title="", caption=""):
        self.photo_id = pid
        self.score = 0.8
        self.title = title or f"t-{pid}"
        self.year = "1930"
        self.location = "广州"
        self.caption = caption


def test_curator_composes_exhibition_json(monkeypatch):
    monkeypatch.setattr(cu.rpipe, "search", lambda q, top_k=12: type(
        "R", (), {"hits": [Hit("a"), Hit("b")], "degraded": set()})())
    captured = {}

    def fake_chat(messages, settings=None, json_mode=False, client_factory=None):
        captured["messages"] = messages
        return ('{"sections": [{"title": "序厅", "narrative": "走进骑楼",'
                ' "photo_ids": ["a", "b"]}]}')

    monkeypatch.setattr(cu.lc, "chat", fake_chat)
    out = cu.compose("骑楼")
    assert out["sections"][0]["photo_ids"] == ["a", "b"]


def test_curator_filters_unknown_photo_ids_and_empty_pool(monkeypatch):
    monkeypatch.setattr(cu.rpipe, "search", lambda q, top_k=12: type(
        "R", (), {"hits": [], "degraded": set()})())
    out = cu.compose("不存在的主题")
    assert out["sections"] == [] and out["refused"] is True

    monkeypatch.setattr(cu.rpipe, "search", lambda q, top_k=12: type(
        "R", (), {"hits": [Hit("a")], "degraded": set()})())
    monkeypatch.setattr(
        cu.lc, "chat",
        lambda *a, **kw: '{"sections":[{"title":"x","narrative":"y","photo_ids":["ghost","a"]}]}',
    )
    out = cu.compose("骑楼")
    assert out["sections"][0]["photo_ids"] == ["a"]


def test_creator_generates_copy_by_type(monkeypatch):
    monkeypatch.setattr(cr, "_hit", lambda pid, settings=None: Hit(pid, "骑楼", "老广州街景"))
    captured = {}

    def fake_chat(messages, settings=None, json_mode=False, client_factory=None):
        captured["messages"] = messages
        return '{"title": "一秒回到1930", "body": "明信片文案"}'

    monkeypatch.setattr(cr.lc, "chat", fake_chat)
    out = cr.create("sample_a", "postcard")
    assert out["type"] == "postcard" and "1930" in out["copy"]["title"]
    assert "骑楼" in str(captured["messages"])


def test_creator_rejects_bad_type():
    import pytest
    with pytest.raises(ValueError):
        cr.create("sample_a", "短视频脚本")
