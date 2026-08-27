"""Commons 爬虫单测：API 解析/版权红线过滤/下载/meta 行组装（全 mock 网络）。"""
import httpx
import pytest

from app.ingest import commons_crawler as cc


SEARCH_JSON = {
    "query": {"search": [
        {"title": "File:Canton 1910 street.jpg"},
        {"title": "File:Unclear painting.png"},
    ]}}

INFO_JSON = {"query": {"pages": {
    "1": {"title": "File:Canton 1910 street.jpg",
          "imageinfo": [{
              "url": "https://upload.example/Canton_1910.jpg",
              "descriptionurl": "https://commons.wikimedia.org/wiki/File:Canton_1910_street.jpg",
              "extmetadata": {
                  "LicenseShortName": {"value": "Public domain"},
                  "DateTimeOriginal": {"value": "1910-01-01"},
                  "ImageDescription": {"value": "一条老街的日常景象"},
              }}]}}}}

PNG_BYTES = b"\x89PNG_fake"


def _transport(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def _ok_handler(req: httpx.Request) -> httpx.Response:
    url = str(req.url)
    if "list=search" in url:
        return httpx.Response(200, json=SEARCH_JSON)
    if "iiprop=" in url:
        if "Unclear" in url:
            return httpx.Response(200, json={"query": {"pages": {}}})
        return httpx.Response(200, json=INFO_JSON)
    if url.startswith("https://upload.example/"):
        from PIL import Image
        from io import BytesIO

        buf = BytesIO()
        Image.new("RGB", (500, 400), (90, 90, 90)).save(buf, format="JPEG")
        return httpx.Response(200, content=buf.getvalue())
    return httpx.Response(404)


def test_crawl_writes_raw_and_rows(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    cli = _transport(_ok_handler)
    rows = cc.crawl(query="Canton 1910", limit=2, location="广州",
                    client=cli, raw_dir=tmp_path / "data/raw")
    assert len(rows) == 1                       # 第二个文件无 imageinfo 被跳过
    r = rows[0]
    assert r["license"] == "Public domain"
    assert r["year"] == "1910"
    assert r["location"] == "广州"
    assert r["source_url"].startswith("https://commons.wikimedia.org/")
    pid = r["photo_id"]
    assert pid.startswith("commons_")
    raw_dir = tmp_path / "data/raw"
    assert list(raw_dir.glob(f"{pid}.*"))


def test_crawl_skips_non_free_license(tmp_path, monkeypatch):
    """版权红线：非 PD/CC0 的图一律跳过，绝不写 meta。"""
    info_cc = {"query": {"pages": {"1": {"title": "File:X.jpg",
               "imageinfo": [{"url": "https://upload.example/x.jpg",
               "descriptionurl": "https://c.org/x",
               "extmetadata": {"LicenseShortName": {"value": "CC BY-SA 4.0"}}}]}}}}

    def handler(req: httpx.Request) -> httpx.Response:
        if "list=search" in str(req.url):
            return httpx.Response(200, json={"query": {"search": [
                {"title": "File:X.jpg"}]}})
        if "iiprop=" in str(req.url):
            return httpx.Response(200, json=info_cc)
        return httpx.Response(200, content=b"jpg")

    monkeypatch.chdir(tmp_path)
    rows = cc.crawl(query="q", limit=1, location="", client=_transport(
        handler), raw_dir=tmp_path / "data/raw")
    assert rows == []


def test_clean_title_drops_suffix():
    assert cc._pid_slug("File:Canton 1910 Street!.jpg") != ""
    import re

    assert re.fullmatch(r"[a-z0-9_]+", cc._pid_slug("File:Canton 街.jpg"))


def test_cli_crawl_smoke_writes_meta(tmp_path, monkeypatch):
    """CLI 骨架冒烟：crawl 子命令把行追加进 meta.csv（网络函数被 mock）。"""
    import csv
    import io

    from app import cli

    monkeypatch.chdir(tmp_path)
    row = {"photo_id": "commons_x_00001", "title": "X",
           "year": "1910", "location": "", 
           "source_url": "https://c.org/x", "license": "CC0"}
    monkeypatch.setattr(cc, "crawl",
                        lambda *a, **k: [row])
    buf = io.StringIO()
    try:
        import contextlib

        with contextlib.redirect_stdout(buf):
            cli.main(["crawl", "--query", "q", "--limit", "1"])
    finally:
        pass
    meta = tmp_path / "data/raw/meta.csv"
    assert meta.exists()
    ids = {r["photo_id"] for r in csv.DictReader(
        meta.open(encoding="utf-8-sig"))}
    assert "commons_x_00001" in ids
