"""Task 3 RED：meta.csv 解析与版权校验（纯函数）。"""
from pathlib import Path

from app.ingest.meta import load_meta

HEADER = "photo_id,title,year,location,source_url,license\n"
ROW_OK = "a1,骑楼街景,1930,广州,http://example.org/a1,Public Domain\n"
ROW_NO_LICENSE = "a2,无证照片,,,,\n"


def _touch(d: Path, name: str) -> None:
    (d / name).touch()


def test_rejects_missing_license(tmp_path):
    (tmp_path / "meta.csv").write_text(HEADER + ROW_OK + ROW_NO_LICENSE, encoding="utf-8")
    _touch(tmp_path, "a1.jpg")
    ok, errors = load_meta(tmp_path / "meta.csv", tmp_path)
    assert [r.photo_id for r in ok] == ["a1"]
    assert any("a2" in e and "license" in e for e in errors)


def test_rejects_empty_source_url(tmp_path):
    row = "a3,缺来源,1920,,,PD\n"  # source_url 为空
    (tmp_path / "meta.csv").write_text(HEADER + ROW_OK + row, encoding="utf-8")
    _touch(tmp_path, "a1.jpg")
    _touch(tmp_path, "a3.jpg")
    ok, errors = load_meta(tmp_path / "meta.csv", tmp_path)
    assert [r.photo_id for r in ok] == ["a1"]
    assert any("a3" in e and "source_url" in e for e in errors)


def test_rejects_missing_image_file(tmp_path):
    (tmp_path / "meta.csv").write_text(HEADER + ROW_OK, encoding="utf-8")  # 无 a1.jpg
    ok, errors = load_meta(tmp_path / "meta.csv", tmp_path)
    assert ok == []
    assert any("a1" in e for e in errors)


def test_accepts_png_jpeg_extensions(tmp_path):
    (tmp_path / "meta.csv").write_text(HEADER + ROW_OK, encoding="utf-8")
    _touch(tmp_path, "a1.png")
    ok, _ = load_meta(tmp_path / "meta.csv", tmp_path)
    assert [r.photo_id for r in ok] == ["a1"]

    _touch(tmp_path, "a1.jpeg")  # jpeg 亦可
    ok2, _ = load_meta(tmp_path / "meta.csv", tmp_path)
    assert len(ok2) == 1


def test_duplicate_photo_id_rejected(tmp_path):
    (tmp_path / "meta.csv").write_text(
        HEADER + ROW_OK + ROW_OK.replace("a1,", "a1,"), encoding="utf-8"
    )
    _touch(tmp_path, "a1.jpg")
    _, errors = load_meta(tmp_path / "meta.csv", tmp_path)
    assert any("重复" in e for e in errors)


def test_fields_mapped_into_record(tmp_path):
    (tmp_path / "meta.csv").write_text(HEADER + ROW_OK, encoding="utf-8")
    _touch(tmp_path, "a1.jpg")
    ok, _ = load_meta(tmp_path / "meta.csv", tmp_path)
    r = ok[0]
    assert r.title == "骑楼街景" and r.year == "1930" and r.location == "广州"
