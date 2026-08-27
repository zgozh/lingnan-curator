"""文创渲染器单测：明信片/海报成功产出 + 缺底图降级 False。"""
from PIL import Image

from app.infra.artifact import render_postcard, render_poster


def _make_src(tmp_path):
    p = tmp_path / "src.jpg"
    Image.new("RGB", (800, 600), (180, 160, 120)).save(p)
    return p


def test_render_postcard_produces_two_pngs(tmp_path):
    src = _make_src(tmp_path)
    front = tmp_path / "postcard-front.png"
    back = tmp_path / "postcard-back.png"
    ok = render_postcard(src, "骑楼老街", "1920", "见字如面，广州的雨落了一整夜。",
                         "馆藏编号 X001 · Public domain", front, back)
    assert ok
    assert front.exists() and back.exists()
    assert Image.open(front).size == (1748, 1181)
    assert Image.open(back).size == (1748, 1181)


def test_render_postcard_missing_src_degrades_false(tmp_path):
    ok = render_postcard(tmp_path / "nope.jpg", "t", "", "b", "m",
                         tmp_path / "f.png", tmp_path / "k.png")
    assert not ok
    assert not (tmp_path / "f.png").exists()


def test_render_postcard_bad_image_file_degrades_false(tmp_path):
    bad = tmp_path / "bad.jpg"
    bad.write_bytes(b"not-an-image")
    assert not render_postcard(bad, "t", "", "b", "m",
                               tmp_path / "f.png", tmp_path / "k.png")


def test_render_poster_produces_png_and_handles_long_slogan(tmp_path):
    src = _make_src(tmp_path)
    out = tmp_path / "slogan.png"
    assert render_poster(src, "一城记忆，百年骑楼在光里重生" * 3, "副题一句话", out)
    assert out.exists()
    assert Image.open(out).size == (1080, 1440)


def test_render_poster_missing_bg_false(tmp_path):
    assert not render_poster(None, "slogan", "sub", tmp_path / "p.png")
