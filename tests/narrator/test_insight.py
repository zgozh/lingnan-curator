from pathlib import Path
from app.narrator.insight import insight
from app.narrator.types import Insight

class FakeVLM:
    def describe(self, image_path, user_prompt, system_prompt=None, json_mode=False, model=None):
        return ('{"scene":"广州骑楼街景","visibles":["骑楼","人力车"],'
                '"characters":[{"who":"小贩","clothing":"唐装","age_hint":"民国"}],'
                '"era_evidence":["骑楼","招牌"],"maybe_place":"广州",'
                '"mood":"热闹","confident_words":"太史第"}')

def test_insight_parses_vlm():
    res = insight(Path("x.jpg"), "title=街景|year=1920|location=广州|caption=骑楼", vlm=FakeVLM())
    assert isinstance(res, Insight)
    assert res.scene == "广州骑楼街景"
    assert res.maybe_place == "广州"
    assert res.source == "vlm" and res.degraded is False
    assert res.characters and res.characters[0].who == "小贩"

class BadVLM:
    def describe(self, image_path, user_prompt, system_prompt=None, json_mode=False, model=None):
        raise RuntimeError("vlm down")

def test_insight_falls_back_to_metadata():
    res = insight(Path("x.jpg"), "title=街景|year=1920|location=广州|caption=骑楼", vlm=BadVLM())
    assert res.degraded is True
    assert res.source == "metadata"
    assert "广州" in res.scene


def test_insight_get_vlm_raise_degrades(monkeypatch):
    """IM-2 回归钉：lc.get_vlm 构造客户端失败（缺 key/import 失败/坏 base_url）
    也必须降级为 metadata Insight，绝不向上抛异常（否则详情页 500）。

    此前 get_vlm 位于 try 之外会漏出；现移入 try 内。
    """
    import app.narrator.insight as ins

    def boom(settings=None):
        raise RuntimeError("vlm client construction failed")

    monkeypatch.setattr(ins.lc, "get_vlm", boom)
    res = insight(Path("x.jpg"), "title=街景|year=1920|location=广州|caption=骑楼")
    assert res.degraded is True
    assert res.source == "metadata"
    assert "广州" in res.scene  # 降级稿来自元数据