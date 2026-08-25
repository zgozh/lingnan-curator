"""T3 RED：检索门面——融合→精排(可降级)→归一→断崖截断。"""
import app.retrieval.pipeline as rp
from app.retrieval.searcher import SearchResult


class Hit:
    def __init__(self, pid, score):
        self.photo_id = pid
        self.score = score
        self.title = f"t-{pid}"
        self.year = ""
        self.location = ""
        self.caption = f"cap-{pid}"


def _mk(pids_scores):
    r = SearchResult()
    for pid, s in pids_scores:
        r.hits.append(Hit(pid, s))
    return r


def _patch(monkeypatch, fused=None):
    monkeypatch.setattr(rp, "get_client", lambda s=None: object())
    monkeypatch.setattr(
        rp, "_raw_search",
        lambda *a, **kw: _mk(fused or [("a", 1.0), ("b", 0.7), ("c", 0.5),
                                       ("d", 0.1)]),
    )


def test_rerank_reorders_when_available(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(rp.rr, "rerank", lambda q, docs, base_url,
                        timeout=5.0: [0.1, 0.9, 0.5, 0.0]
                        if len(docs) == 4 else None)
    out = rp.search("骑楼", top_k=4, base_url="http://x")
    # 精排重排为 b>c>a>d；d 归一后 0.0 < 断崖阈值(1.0×0.35) 被截掉
    assert [h.photo_id for h in out.hits] == ["b", "c", "a"]
    assert "rerank" not in out.degraded


def test_rerank_unavailable_marks_degraded_keeps_order(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(rp.rr, "rerank", lambda *a, **kw: None)
    out = rp.search("骑楼", top_k=4, base_url="http://x")
    assert [h.photo_id for h in out.hits] == ["a", "b", "c"]
    assert "rerank" in out.degraded


def test_cliff_cutoff_drops_low_scores(monkeypatch):
    _patch(monkeypatch)
    monkeypatch.setattr(rp.rr, "rerank", lambda *a, **kw: None)
    out = rp.search("骑楼", top_k=8, base_url="http://x")
    ids = [h.photo_id for h in out.hits]
    assert "d" not in ids  # 0.1 < 1.0×0.35 → 断崖截掉


def test_cliff_caps_at_twelve(monkeypatch):
    many = [(f"p{i}", 1.0 - i * 0.01) for i in range(20)]
    _patch(monkeypatch, fused=many)
    monkeypatch.setattr(rp.rr, "rerank", lambda *a, **kw: None)
    out = rp.search("骑楼", top_k=50, base_url="http://x")
    assert len(out.hits) <= 12
