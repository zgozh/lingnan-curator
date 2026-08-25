"""F2 检索门面：融合 → qwen3-rerank 精排(可降级) → 归一 → 断崖截断(动态 top-k)。

降级语义（spec 边界案例）：rerank 不可用 → 融合排序直出，degraded 含 'rerank'；
断崖阈值 = 最高分 × 0.35，且硬上限 12 条。
"""
import logging
from dataclasses import dataclass, field

from app.config import Settings
from app.infra import reranker as rr
from app.infra.embedder import Embedder
from app.infra.milvus_store import get_client
from app.retrieval import searcher

logger = logging.getLogger(__name__)

_CLIFF_RATIO = 0.35
_HARD_CAP = 12


@dataclass
class SearchHit:
    photo_id: str
    score: float
    title: str = ""
    year: str = ""
    location: str = ""
    caption: str = ""


@dataclass
class SearchResult:
    hits: list[SearchHit] = field(default_factory=list)
    degraded: set[str] = field(default_factory=set)


def _raw_search(client, query, collection, top_k, image_path) -> SearchResult:
    return searcher.search(client, Embedder(), collection, query,
                           top_k=top_k, image_path=image_path)


def search(query: str, top_k: int = 8, image_path=None,
           settings: Settings | None = None,
           base_url: str | None = None) -> SearchResult:
    s = settings or Settings.load()
    client = get_client(s)
    raw = _raw_search(client, query, s.collection, max(top_k * 2, 10),
                      image_path)
    result = SearchResult(degraded=set(raw.degraded))

    hits = list(raw.hits)
    base = base_url if base_url is not None else getattr(s, "rerank_base_url",
                                                         None)
    if hits:
        docs = [f"{h.title} {h.caption}".strip() for h in hits]
        scores = rr.rerank(query, docs, base_url=base)
        if scores is not None:
            order = sorted(range(len(hits)), key=lambda i: scores[i],
                           reverse=True)
            hits = [hits[i] for i in order]
            norm = searcher.normalize([scores[i] for i in order])
            hits = [h for h, nsc in zip(hits, norm)]
            hits = [
                SearchHit(h.photo_id, round(nsc, 4), h.title, h.year,
                          h.location, h.caption)
                for h, nsc in zip(hits, norm)
            ]
        else:
            result.degraded.add("rerank")

    # 断崖截断：相对最高分的弱结果直接丢弃；再套硬上限
    if hits:
        peak = max(h.score for h in hits)
        kept = [h for h in hits if h.score >= peak * _CLIFF_RATIO]
        result.hits = kept[:_HARD_CAP]
    else:
        result.hits = []
    return result
