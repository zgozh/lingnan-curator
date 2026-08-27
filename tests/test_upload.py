"""上传通道单测：字段校验/pid 生成/meta 追加/后台入库触发/路径安全。"""
import shutil
from pathlib import Path

import pytest
from PIL import Image
from io import BytesIO

import app.web.main as wm


def _client(monkeypatch):
    monkeypatch.setattr(wm, "_photos_all", lambda: [])
    monkeypatch.setattr(
        wm, "_health_flags",
        lambda: {"milvus": True, "rerank": False})
    return __import__("fastapi.testclient", fromlist=["TestClient"]).\
        TestClient(wm.create_app())


@pytest.fixture()
def workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data/raw").mkdir(parents=True)
    (tmp_path / "data/processed").mkdir(parents=True)
    return tmp_path


def _png_bytes(color=(10, 100, 200)):
    buf = BytesIO()
    Image.new("RGB", (400, 300), color).save(buf, format="PNG")
    return buf.getvalue()


def _post(client, *, fields=None, filename="a.png", content=None,
          monkeypatch=None, spawned=None):
    if spawned is None:
        spawned = []
    monkeypatch.setattr(wm, "_spawn_ingest", lambda pid: spawned.append(pid))
    files = {"file": (filename, content or _png_bytes(), "image/png")}
    r = client.post("/api/upload", data=fields or {
        "title": "骑楼新照", "license": "Public domain",
        "source_url": "https://example.com/x.jpg"},
        files=files)
    return r, spawned


def test_upload_ok_writes_raw_and_meta_and_spawns(workspace, monkeypatch):
    c = _client(monkeypatch)
    r, spawned = _post(c, monkeypatch=monkeypatch)
    assert r.status_code == 200, r.text
    body = r.json()
    pid = body["photo_id"]
    assert pid.startswith("user_")
    assert (workspace / f"data/raw/{pid}.png").exists()
    meta = (workspace / "data/raw/meta.csv").read_text(encoding="utf-8")
    assert pid in meta and "Public domain" in meta
    assert spawned == [pid]


def test_upload_missing_license_rejected(workspace, monkeypatch):
    """版权红线：缺 license 的上传必须被拒绝。"""
    c = _client(monkeypatch)
    r, spawned = _post(c, monkeypatch=monkeypatch,
                       fields={"title": "x", "source_url": "https://e.com"})
    assert r.status_code == 400
    assert "license" in r.text.lower() or "许可" in r.text
    assert spawned == []


def test_upload_missing_source_url_rejected(workspace, monkeypatch):
    c = _client(monkeypatch)
    r, _ = _post(c, monkeypatch=monkeypatch,
                 fields={"title": "x", "license": "CC0"})
    assert r.status_code == 400


def test_upload_non_image_rejected(workspace, monkeypatch):
    c = _client(monkeypatch)
    r, _ = _post(c, monkeypatch=monkeypatch,
                 content=b"not an image", filename="fake.png")
    assert r.status_code == 400


def test_upload_bad_ext_rejected(workspace, monkeypatch):
    c = _client(monkeypatch)
    r, _ = _post(c, monkeypatch=monkeypatch, filename="a.gif")
    assert r.status_code == 400


def test_upload_duplicate_pid_gets_unique_suffix(workspace, monkeypatch):
    c = _client(monkeypatch)
    r1, _ = _post(c, monkeypatch=monkeypatch)
    r2, _ = _post(c, monkeypatch=monkeypatch,
                  fields={"title": "骑楼新照", "license": "CC0",
                          "source_url": "https://e.com/y.jpg"})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["photo_id"] != r2.json()["photo_id"]


def test_pid_slug_safe_chars_only(workspace, monkeypatch):
    c = _client(monkeypatch)
    r, _ = _post(c, monkeypatch=monkeypatch,
                 fields={"title": "我的 骑楼照!! 2024", "license": "CC0",
                         "source_url": "https://e.com/z.jpg"})
    import re

    assert re.fullmatch(r"[A-Za-z0-9_\-]+", r.json()["photo_id"])
