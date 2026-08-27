"""enhance 云链单测：缩图→修褶皱→上色→回贴 锚定关键契约。

refine_image 打桩捕获调用序列；失败任一步必须不产出 enhanced.jpg。
"""
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


class FakeChain:
    """替身 refine_image：记录调用并伪写结果小图。"""

    def __init__(self, fail_at=None):
        self.calls = []
        self.fail_at = fail_at

    def __call__(self, src, dst, function=None, prompt="", settings=None,
                 **kw):
        self.calls.append({"function": function, "src": str(src),
                           "prompt_len": len(prompt)})
        if self.fail_at == function:
            return False
        Image.new("RGB", (1392, 736), (180, 170, 120)).save(dst)
        return True


def test_chain_produces_enhanced_and_calls_in_order(demo_root):
    from app.ingest import enhance

    fake = FakeChain()
    ok = enhance.build_enhanced("gz_demo", settings=None, refine=fake)
    assert ok
    assert [c["function"] for c in fake.calls] == \
        ["description_edit", "colorization"]
    # 修复步提示词必须含褶皱要求；上色步必须禁怀旧黄调
    out = demo_root / "enhanced.jpg"
    assert out.exists()
    im = Image.open(out)
    assert im.size[0] >= 2400            # 回贴放大目标下限
    # 输入已预缩到接口限制内（长边 ≤1600）
    assert fake.calls[0]["prompt_len"] > 10


def test_repair_step_failure_yields_no_file(demo_root):
    from app.ingest import enhance

    fake = FakeChain(fail_at="description_edit")
    assert not enhance.build_enhanced("gz_demo", settings=None, refine=fake)
    assert not (demo_root / "enhanced.jpg").exists()


def test_color_step_failure_yields_no_file(demo_root):
    from app.ingest import enhance

    fake = FakeChain(fail_at="colorization")
    assert not enhance.build_enhanced("gz_demo", settings=None, refine=fake)


def test_missing_restored_returns_false(tmp_path, monkeypatch):
    from app.ingest import enhance

    monkeypatch.chdir(tmp_path)
    (tmp_path / "p_nox").mkdir()
    assert not enhance.build_enhanced(
        "p_nox", settings=None, refine=FakeChain())
