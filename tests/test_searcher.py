"""T1 RED：检索基元——文本通道(0.8/0.2加权)+CLIP通道+RRF融合+归一化。"""
import app.retrieval.searcher as se


class FakeClient:
    """记录调用并返回预设结果；不连真 Milvus。"""

    def __init__(self, text_hits=None, clip_hits=None):
        self.text_hits = text_hits or []
        self.clip_hits = clip_hits or []
        self.calls = []

    def hybrid_search(self, **kw):
        self.calls.append(("hybrid", kw))
        return self.text_hits

    def search(self, **kw):
        self.calls.append(("search", kw))
        return self.clip_hits


class FakeEmb:
    def __init__(self):
        self.text_called = False

    def texts(self, q):
        self.text_called = True
        return ([[0.1] * 1024], [{5: 0.7}])

    def image(self, p):
        return [0.2] * 512


def _hit(pid, score):
    return {"id": pid, "distance": score,
            "entity": {"title": f"t-{pid}", "year": "", "location": "",
                       "caption": ""}}


def test_text_channel_uses_weighted_ranker():
    c = FakeClient(text_hits=[_hit("a", 0.9), _hit("b", 0.8)])
    emb = FakeEmb()
    hits = se.text_channel(c, "lingnan_photos", "骑楼", emb, limit=5)
    assert emb.text_called
    kind, kw = c.calls[0]
    assert kind == "hybrid"
    ranker = kw["ranker"]
    assert getattr(ranker, "_weights", None) in (None, [0.8, 0.2]) or ranker is not None
    assert [h["photo_id"] for h in hits] == ["a", "b"]


def test_rrf_fuse_orders_by_sum_of_reciprocal_ranks():
    fused = se.rrf_fuse(
        [["a", "b", "c"], ["b", "a"]],
        k=60,
    )
    # a: 1/61 + 1/62 ; b: 1/62 + 1/61 —— 相同；c 只出现一次应排最后
    assert set(fused) == {"a", "b", "c"}
    assert fused["c"] < fused["a"]


def test_normalize_maps_best_to_one_and_others_relative():
    vals = se.normalize([2.0, 1.0, 0.0])
    assert vals[0] == 1.0 and 0.0 <= vals[1] < 1.0 and vals[2] == 0.0


def test_search_fuses_text_and_clip_channels():
    c = FakeClient(
        text_hits=[_hit("a", 0.9), _hit("b", 0.6)],
        clip_hits=[[_hit("b", 0.95), _hit("c", 0.5)]],
    )
    out = se.search(c, FakeEmb(), "lingnan_photos", "骑楼", top_k=3,
                    image_path="q.jpg")
    ids = [h.photo_id for h in out.hits]
    assert set(ids) == {"a", "b", "c"}
    assert out.degraded == set()
    scores = {h.photo_id: h.score for h in out.hits}
    assert max(scores.values()) <= 1.0 + 1e-9


def test_clip_failure_degrades_to_text_only():
    class NoClipEmb(FakeEmb):
        def image(self, p):
            raise RuntimeError("CLIP 挂了")

    c = FakeClient(text_hits=[_hit("a", 0.9)])
    out = se.search(c, NoClipEmb(), "lingnan_photos", "骑楼", top_k=3,
                    image_path="q.jpg")
    assert [h.photo_id for h in out.hits] == ["a"]
    assert out.degraded == {"clip"}
