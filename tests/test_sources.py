"""多来源抓取适配器单测：Openverse 解析/许可过滤 + 来源注册表降级。"""
import httpx

from app.ingest import openverse_provider as ov
from app.ingest import sources


def _ov_json():
    return {
        "results": [
            {"title": "Canton Pagoda 1910.jpg",
             "url": "https://img.example/pagoda.jpg",
             "foreign_landing_url": "https://foo.example/rec1",
             "license": "pdm", "license_version": None},
            {"title": "Modern snapshot.jpg",
             "url": "https://img.example/snap.jpg",
             "foreign_landing_url": "https://foo.example/rec2",
             "license": "by-nc-sa", "license_version": "4.0"},
        ]}


def _handler(req: httpx.Request) -> httpx.Response:
    url = str(req.url)
    if url.startswith("https://img.example/"):
        from PIL import Image
        from io import BytesIO

        buf = BytesIO()
        Image.new("RGB", (480, 360), (120, 90, 60)).save(
            buf, format="JPEG")
        return httpx.Response(200, content=buf.getvalue())
    if "/v1/images/" in url:
        return httpx.Response(200, json=_ov_json())
    return httpx.Response(404)


def test_openverse_keeps_only_free_license(tmp_path):
    """版权红线：CC BY-NC-SA 等非公版必须被跳过。"""
    cli = httpx.Client(transport=httpx.MockTransport(_handler))
    rows = ov.crawl_openverse("Canton 1910", limit=5, location="广州",
                              client=cli, raw_dir=tmp_path / "data/raw")
    assert len(rows) == 1
    r = rows[0]
    assert r["photo_id"].startswith("ov_")
    assert "Public domain" in r["license"]
    assert r["source_url"] == "https://foo.example/rec1"
    assert list((tmp_path / "data/raw").glob(r["photo_id"] + ".*"))


def test_registry_routes_and_degrades(tmp_path, monkeypatch):
    """已知来源路由到实现；未知来源返回空行+日志（不抛异常）。"""
    called = {}

    def fake_commons(query, limit, location, client, raw_dir):
        called["q"] = query
        return [{"photo_id": "commons_x_00001", "title": "X",
                 "year": "", "location": "", "source_url": "u",
                 "license": "Public domain"}]

    monkeypatch.setattr(sources, "_crawl_commons", fake_commons)
    rows, logs = sources.run_source("commons", "q", 3, "广州",
                                    tmp_path / "raw")
    assert rows and called["q"] == "q"
    rows2, logs2 = sources.run_source("bogus-source", "q", 3, "",
                                      tmp_path / "raw")
    assert rows2 == [] and any("bogus" in log for log in logs2)
