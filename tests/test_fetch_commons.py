"""fetch_commons 纯函数测试：许可白名单/年份提取/slug。"""
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
