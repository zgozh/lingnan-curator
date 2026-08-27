"""enhance E2 链单测：单步上色 + 亮度合成保脸契约。"""
import io

import pytest
from PIL import Image


@pytest.fixture()
def demo_root(tmp_path, monkeypatch):
    root = tmp_path / "data" / "processed" / "gz_demo"
    root.mkdir(parents=True)
    Image.new("RGB", (3840, 2066), (150, 150, 150)).save(root / "restored.jpg")
    monkeypatch.chdir(tmp_path)
    return root


class FakeColor:
    """替身 refine_image：只认 colorization；伪写彩色小图。"""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, src, dst, function=None, prompt="", settings=None,
                 **kw):
        self.calls.append(function)
        if self.fail:
            return False
        Image.new("RGB", (1392, 736), (180, 170, 120)).save(dst)
        return True


def test_single_color_call_and_composite_output(demo_root):
    from app.ingest import enhance

    fake = FakeColor()
    ok = enhance.build_enhanced("gz_demo", settings=None, refine=fake)
    assert ok
    # 红线：绝不允许 description_edit（会幻改人脸）
    assert fake.calls == ["colorization"]
    out = demo_root / "enhanced.jpg"
    assert out.exists()
    im = Image.open(out)
    assert im.size[0] >= 2400


def test_structure_preserved_when_local_is_stripey(demo_root):
    """亮度结构来自本地：本地图横条纹必须保留在 enhanced 的 Y 通道中。"""
    from app.ingest import enhance

    stripe = Image.new("L", (2880, 1546))
    for y_ in range(stripe.size[1]):
        v = 90 if (y_ // 64) % 2 else 190
        for x in range(stripe.size[0]):
            stripe.putpixel((x, y_), v)
    stripe.convert("RGB").save(demo_root / "restored.jpg")
    fake = FakeColor()
    assert enhance.build_enhanced("gz_demo", settings=None, refine=fake)
    got = Image.open(demo_root / "enhanced.jpg").convert("YCbCr").split()[0]
    col = [got.getpixel((5, y)) for y in range(0, got.size[1], 2)]
    assert max(col) - min(col) > 40   # 纵向条纹对比仍在 → 结构未被动过


def test_color_step_failure_yields_no_file(demo_root):
    from app.ingest import enhance

    assert not enhance.build_enhanced(
        "gz_demo", settings=None, refine=FakeColor(fail=True))
    assert not (demo_root / "enhanced.jpg").exists()


def test_missing_restored_returns_false(tmp_path, monkeypatch):
    from app.ingest import enhance

    monkeypatch.chdir(tmp_path)
    (tmp_path / "data" / "processed" / "p_nox").mkdir(parents=True)
    assert not enhance.build_enhanced(
        "p_nox", settings=None, refine=FakeColor())


def test_composite_helper_sizes_align():
    from app.ingest.enhance import _composite

    ref = Image.new("RGB", (3840, 2066), (128, 128, 128))
    cloud = Image.new("RGB", (1392, 736), (200, 100, 50))
    out = _composite(ref, cloud)
    assert out.size == cloud.size
