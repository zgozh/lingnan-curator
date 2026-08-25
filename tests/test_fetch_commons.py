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
