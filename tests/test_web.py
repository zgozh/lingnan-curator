"""T7 RED：Web 展馆——页面/健康检查降级/SSE/create 错误映射。"""
from fastapi.testclient import TestClient

import app.web.main as wm


def _client(monkeypatch, *, milvus_ok=True) -> TestClient:
    monkeypatch.setattr(wm, "_photos_all", lambda: [
        {"photo_id": "sample_a", "title": "骑楼A", "year": "1930",
         "location": "广州"},
    ])
    monkeypatch.setattr(
        wm, "_health_flags",
        lambda: {"milvus": milvus_ok, "rerank": False},
    )
    monkeypatch.setattr(wm.rpipe, "search", lambda q, top_k=8: type(
        "R", (), {"hits": [type("H", (), {
            "photo_id": "sample_a", "score": 0.9, "title": "骑楼A",
            "year": "1930", "location": "广州", "caption": "老街"})()],
            "degraded": set()})())
    # 详情页只读缓存（_read_story）；必须 mock，避免真实文件系统依赖。
    # 页面不触发生成——生成走 /api/narrate，此处不需要 mock run_story_chain。
    monkeypatch.setattr(
        wm, "_read_story",
        lambda base: ("一个广州的老故事。",
                      [{"text": "旁白", "emotion": "怀念"}]),
    )
    return TestClient(wm.create_app())


def test_index_lists_photos(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/")
    assert r.status_code == 200
    assert "骑楼A" in r.text


def test_index_shows_milvus_down_banner(monkeypatch):
    c = _client(monkeypatch, milvus_ok=False)
    r = c.get("/")
    assert r.status_code == 200
    assert "Docker Desktop" in r.text and "19530" in r.text  # 中文提示+启动指引


def test_search_page_renders_hits(monkeypatch):
    c = _client(monkeypatch)
    r = c.get("/search", params={"q": "骑楼"})
    assert r.status_code == 200
    assert "sample_a" in r.text


def test_health_endpoint(monkeypatch):
    c = _client(monkeypatch)
    data = c.get("/api/health").json()
    assert data == {"milvus": True, "rerank": False}


def test_ask_sse_stream(monkeypatch):
    def fake_stream(question, settings=None):
        yield {"type": "delta", "text": "你好"}
        yield {"type": "done", "refused": False, "photo_ids": ["sample_a"]}
    monkeypatch.setattr(wm.docent, "stream_answer", fake_stream)
    c = _client(monkeypatch)
    with c.stream("POST", "/api/ask", json={"q": "骑楼"}) as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        body = "".join(r.iter_text())
    assert '"delta"' in body and "done" in body


def test_create_copy_maps_errors(monkeypatch):
    monkeypatch.setattr(wm.creator, "create",
                        lambda pid, t, settings=None: {"ok": True})
    c = _client(monkeypatch)
    assert c.post("/api/create/sample_a", json={"type": "postcard"}).status_code == 200

    def bad_type(pid, t, settings=None):
        raise ValueError("bad type")
    monkeypatch.setattr(wm.creator, "create", bad_type)
    assert c.post("/api/create/sample_a",
                  json={"type": "x"}).status_code == 400

    def missing(pid, t, settings=None):
        raise LookupError("no photo")
    monkeypatch.setattr(wm.creator, "create", missing)
    assert c.post("/api/create/nope",
                  json={"type": "postcard"}).status_code == 404


def test_narrate_api_voice_override_and_errors(monkeypatch):
    """换音色重新合成：委托给 run_story_chain(force=True, voice=voice)。

    校验：合法音色 → 200 + force=True + voice 透传；非法音色 → 400；
    空 body → 200 + voice=None（降级回默认音色）。
    """
    captured = {}

    def fake_chain(photo_id, force=False, voice=None, **kwargs):
        captured.update(photo_id=photo_id, force=force, voice=voice)
        return {"audio": True, "degraded": False}

    # 先建 client（_client 会先用默认 lambda 覆盖 run_story_chain），
    # 再覆盖为捕获版：api_narrate 在请求时按模块全局查找，故此处仍生效。
    c = _client(monkeypatch)
    monkeypatch.setattr(wm, "run_story_chain", fake_chain)

    r = c.post("/api/narrate/sample_a", json={"voice": "longanyue"})
    assert r.status_code == 200
    assert captured["photo_id"] == "sample_a"
    assert captured["force"] is True
    assert captured["voice"] == "longanyue"

    r2 = c.post("/api/narrate/sample_a", json={"voice": "不存在的音色"})
    assert r2.status_code == 400  # 校验前置：非法音色仍拦下，不触达链

    r3 = c.post("/api/narrate/sample_a", json={})
    assert r3.status_code == 200
    assert captured["voice"] is None


def test_detail_page_lists_cantonese_voices(monkeypatch):
    from app.infra.tts import VOICES
    monkeypatch.setattr(
        wm, "_photos_all", lambda: [
            {"photo_id": "sample_a", "title": "骑楼A", "year": "1930",
             "location": "广州"}])
    monkeypatch.setattr(wm, "_get_photo",
                        lambda pid, settings=None: {
                            "photo_id": pid, "title": "骑楼A",
                            "caption": "c", "has_colorized": 0})
    monkeypatch.setattr(wm, "_health_flags",
                        lambda: {"milvus": True})
    c = _client(monkeypatch)
    body = c.get("/photo/sample_a").text
    for vid in VOICES:
        assert vid in body


def test_detail_renders_chinese_creator_labels(monkeypatch):
    """文创三个类型按钮应为中文标签（非英文 postcard/slogan/moments）。"""
    monkeypatch.setattr(wm, "_get_photo",
                        lambda pid, settings=None: {
                            "photo_id": pid, "title": "骑楼A",
                            "caption": "c", "has_colorized": 0})
    c = _client(monkeypatch)
    body = c.get("/photo/sample_a").text
    for label in ("明信片", "标语", "朋友圈文案"):
        assert label in body
    assert "postcard" in body  # 仍以 data-type 属性存在，供前端识别


def test_detail_always_has_narration_audio_element(monkeypatch):
    """即便已生成音频元素，未合成时也须渲染 audio 节点（免刷新热更新）。"""
    monkeypatch.setattr(wm, "_get_photo",
                        lambda pid, settings=None: {
                            "photo_id": pid, "title": "骑楼A",
                            "caption": "c", "has_colorized": 0})
    c = _client(monkeypatch)
    body = c.get("/photo/sample_a").text
    assert 'id="narration-audio"' in body


def test_detail_renders_story_and_narration(monkeypatch):
    """详情页应渲染缓存的故事文本 + 逐句旁白（含 emotion）。"""
    monkeypatch.setattr(wm, "_get_photo",
                        lambda pid, settings=None: {
                            "photo_id": pid, "title": "骑楼A",
                            "caption": "c", "has_colorized": 0})
    c = _client(monkeypatch)
    body = c.get("/photo/sample_a").text
    assert "一个广州的老故事。" in body
    assert "旁白" in body
    assert 'data-emotion="怀念"' in body
