"""fetch_commons 纯函数测试：许可白名单/年份提取/slug。"""
import io
import json
import urllib.error
from email.message import Message

import pytest

import scripts.fetch_commons as fc


def test_license_whitelist():
    assert fc._license_ok("Public domain")
    assert fc._license_ok("CC0")
    assert fc._license_ok("CC BY 4.0")
    assert fc._license_ok("CC BY-SA 3.0")  # SA 可接受（传染但允许商用）
    assert not fc._license_ok("CC BY-NC 4.0")
    assert not fc._license_ok("CC BY-ND 2.0")
    assert not fc._license_ok("Fair use")
    assert not fc._license_ok("")
    assert not fc._license_ok(None)


def test_year_extraction():
    assert fc._year_from("1930-05-01") == "1930"
    assert fc._year_from("circa 1928") == "1928"
    assert fc._year_from("unknown") == ""
    assert fc._year_from("") == ""


def test_slug_unique_and_ascii():
    a = fc._slug("广州骑楼街景", 1)
    b = fc._slug("广州骑楼街景", 2)
    assert a != b and a.startswith("gz_") and ".j" not in a


def test_dedup_against_existing(tmp_path):
    import csv
    csv_path = tmp_path / "meta.csv"
    csv_path.write_text(
        "photo_id,title,year,location,license,source_url\n"
        "gz_1,旧图,1930,广州,Public domain,https://x/1\n",
        encoding="utf-8")
    from pathlib import Path
    assert "gz_1" in fc._existing_ids(Path(csv_path))


def test_append_aligns_existing_header_order(tmp_path, monkeypatch):
    """已有 meta.csv 列序与脚本默认不同时，追加行必须对齐现有表头。"""
    import csv
    meta = tmp_path / "meta.csv"
    meta.write_text(
        "photo_id,title,year,location,source_url,license\n"
        "sample_a,冒烟A,1930,广州,local-smoke,TEMP-DEMO\n",
        encoding="utf-8")
    monkeypatch.setattr(fc, "RAW", tmp_path)
    monkeypatch.setattr(fc, "META", meta)

    info = {"title": "File:Foo Bar.jpg", "thumb": "https://x/t.jpg",
            "width": 1600, "mime": "image/jpeg", "license": "Public domain",
            "date": "1930-01-01",
            "page": "https://commons.wikimedia.org/wiki/File:Foo_Bar.jpg"}
    monkeypatch.setattr(fc, "_file_titles",
                        lambda opener, cat, search, limit: iter(["File:Foo Bar.jpg"]))
    monkeypatch.setattr(fc, "_info", lambda opener, title, width: info)
    monkeypatch.setattr(fc, "_download",
                        lambda opener, url, dest: (dest.write_bytes(b"x" * 20480) or True))

    fc.main(["--category", "Historical_images_of_Guangzhou",
             "--limit", "5", "--location", "广州"])

    with open(meta, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    added = [r for r in rows if r["photo_id"] != "sample_a"]
    assert len(added) == 1
    # 列错位回归：license 列必须仍是许可名，source_url 必须是链接
    assert added[0]["license"] == "Public domain"
    assert added[0]["source_url"].startswith("https://commons.wikimedia.org/")
    assert added[0]["title"] == "Foo Bar.jpg"


class _Resp:
    def __init__(self, payload):
        self._p = json.dumps(payload).encode("utf-8")

    def read(self):
        return self._p

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _FlakyOpener:
    """按序返回预设响应/异常，模拟 429 限流。"""

    def __init__(self, responses):
        self._rs = list(responses)

    def open(self, req, timeout=None):
        r = self._rs.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def _http_error(code):
    return urllib.error.HTTPError(
        "https://commons.wikimedia.org/w/api.php", code, "err", Message(),
        io.BytesIO(b""))


def test_api_retries_on_429(monkeypatch):
    monkeypatch.setattr(fc.time, "sleep", lambda s: None)
    op = _FlakyOpener([_http_error(429), _http_error(500),
                       _Resp({"query": {"pages": {}}})])
    data = fc._api(op, action="query", titles="File:X.jpg")
    assert data == {"query": {"pages": {}}}


def test_api_gives_up_after_tries(monkeypatch):
    monkeypatch.setattr(fc.time, "sleep", lambda s: None)
    op = _FlakyOpener([_http_error(429)] * 8)
    with pytest.raises(urllib.error.HTTPError):
        fc._api(op, action="query", titles="File:X.jpg")


def test_api_error_skips_title_and_continues(tmp_path, monkeypatch):
    """单张 imageinfo 失败(如 429 重试耗尽)只跳过该张，不拖垮整批。"""
    good = {"title": "File:Good.jpg", "thumb": "https://x/t.jpg",
            "width": 1600, "mime": "image/jpeg", "license": "CC BY-SA 3.0",
            "date": "1930-01-01",
            "page": "https://commons.wikimedia.org/wiki/File:Good.jpg"}

    def fake_info(opener, title, width):
        if title == "File:Bad.jpg":
            raise _http_error(429)
        return good

    monkeypatch.setattr(fc, "RAW", tmp_path)
    monkeypatch.setattr(fc, "META", tmp_path / "meta.csv")
    monkeypatch.setattr(fc, "_file_titles",
                        lambda o, c, s, l: iter(
                            ["File:Good.jpg", "File:Bad.jpg",
                             "File:Good 2.jpg"]))
    monkeypatch.setattr(fc, "_info", fake_info)
    monkeypatch.setattr(fc, "_download",
                        lambda o, u, d: (d.write_bytes(b"x" * 20480) or True))
    monkeypatch.setattr(fc.time, "sleep", lambda s: None)

    fc.main(["--category", "X", "--limit", "5", "--location", "广州"])  # 不抛

    import csv
    with open(tmp_path / "meta.csv", encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 2  # Bad 被跳过，前后两张都入库
    assert all(r["photo_id"].startswith("gz_") for r in rows)
    assert all(r["license"] == "CC BY-SA 3.0" for r in rows)


def test_stdout_survives_gbk_console(tmp_path, monkeypatch):
    """标题含 GBK 外字符(如 œ)时打印不得让脚本崩溃(替换为 ?)。"""
    import io as _io
    fake_out = _io.TextIOWrapper(_io.BytesIO(), encoding="gbk",
                                 errors="strict")
    monkeypatch.setattr(fc.sys, "stdout", fake_out)
    fc._safe_print("  [OK] Grant Hall œuvre")
    fake_out.flush()
    assert b"?uvre" in fake_out.buffer.getvalue()
