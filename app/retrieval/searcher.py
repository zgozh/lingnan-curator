"""F2 检索基元：文本通道(BGE-M3 dense+sparse 加权) + CLIP 通道 → RRF 融合 → 归一化。

打分配方沿用 architecture.md/DocMind：COSINE 0.8 + IP 0.2（通道内加权），
两通道结果再做 RRF(k=60) 融合；对外只输出归一化分数 [0,1]。
本模块不做降级决策以外的业务判断（架构分层约束）。
"""
import logging
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

_TEXT_WEIGHTS = (0.8, 0.2)  # dense COSINE : sparse IP
_OUTPUT_FIELDS = ["title", "year", "location", "caption"]


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


def text_channel(client, collection: str, query: str, embedder, limit: int) -> list[dict]:
    """BGE-M3 dense+sparse 双路加权检索；返回原始命中 dict 列表。"""
    dense, sparse = embedder.texts(query)
    from pymilvus import AnnSearchRequest, WeightedRanker

    reqs = [
        AnnSearchRequest(
            data=[dense[0]], anns_field="emb_dense",
            param={"metric_type": "COSINE"}, limit=limit,
        ),
        AnnSearchRequest(
            data=[sparse[0]], anns_field="emb_sparse",
            param={"metric_type": "IP"}, limit=limit,
        ),
    ]
    rows = client.hybrid_search(
        collection_name=collection, reqs=reqs,
        ranker=WeightedRanker(*_TEXT_WEIGHTS),
        limit=limit, output_fields=_OUTPUT_FIELDS,
    )
    return [_row_to_dict(r) for r in _flatten(rows)]


def clip_channel(client, collection: str, image_path, embedder, limit: int) -> list[dict]:
    """CLIP 图像向量检索；embedder 失败由调用方决定降级。"""
    vec = embedder.image(image_path)
    rows = client.search(
        collection_name=collection, data=[vec], anns_field="emb_clip",
        param={"metric_type": "COSINE"}, limit=limit,
        output_fields=_OUTPUT_FIELDS,
    )
    return [_row_to_dict(r) for r in _flatten(rows)]


def _flatten(rows) -> list:
    """pymilvus 返回可能是 SearchResult[HybridHits[dict]] 容器套容器。"""
    try:
        first = rows[0]
        if hasattr(first, "__iter__") and not isinstance(first, dict):
            return list(first)
    except Exception:  # noqa: BLE001 —— 结构探测失败按平铺处理
        pass
    return list(rows)


def _row_to_dict(row) -> dict:
    if isinstance(row, dict):
        entity = row.get("entity", {})
        return {"photo_id": row.get("id"), "score": row.get("distance"),
                **entity}
    entity = getattr(row, "entity", {}) or {}
    return {"photo_id": getattr(row, "id", None),
            "score": getattr(row, "distance", 0.0), **entity}


def rrf_fuse(rank_lists: list[list[str]], k: int = 60) -> dict[str, float]:
    """Reciprocal Rank Fusion：score = Σ 1/(k+rank)；未出现的通道不贡献。"""
    fused: dict[str, float] = {}
    for ranks in rank_lists:
        for i, pid in enumerate(ranks):
            fused[pid] = fused.get(pid, 0.0) + 1.0 / (k + i + 1)
    return fused


def normalize(scores: list[float]) -> list[float]:
    """min-max 归一到 [0,1]；全等时返回全 1（避免除零）。"""
    if not scores:
        return []
    lo, hi = min(scores), max(scores)
    span = hi - lo
    if span <= 1e-12:
        return [1.0] * len(scores)
    return [(s - lo) / span for s in scores]


def search(client, embedder, collection: str, query: str,
           top_k: int = 8, image_path=None) -> SearchResult:
    """两通道融合检索；CLIP 失败自动降级纯文本（degraded={'clip'}）。"""
    text_rows = text_channel(client, collection, query, embedder,
                             limit=max(top_k * 2, 10))
    result = SearchResult()
    rank_lists = [[r["photo_id"] for r in text_rows]]
    all_rows: dict[str, dict] = {r["photo_id"]: r for r in text_rows}

    if image_path is not None:
        try:
            clip_rows = clip_channel(client, collection, image_path,
                                     embedder, limit=max(top_k * 2, 10))
            rank_lists.append([r["photo_id"] for r in clip_rows])
            for r in clip_rows:
                all_rows.setdefault(r["photo_id"], r)
        except Exception as exc:  # noqa: BLE001 —— spec 边界案例：CLIP 挂→纯文本
            logger.warning("CLIP 通道失败，降级纯文本: %s", exc)
            result.degraded.add("clip")

    fused = rrf_fuse(rank_lists)
    pids = sorted(fused, key=fused.__getitem__, reverse=True)[:top_k]
    scores = normalize([fused[p] for p in pids])
    for pid, s in zip(pids, scores):
        row = all_rows.get(pid, {})
        result.hits.append(SearchHit(
            photo_id=pid, score=round(s, 4),
            title=row.get("title") or "", year=row.get("year") or "",
            location=row.get("location") or "",
            caption=row.get("caption") or "",
        ))
    return result
