"""qwen3-rerank 精排客户端：HTTP 服务封装；失败一律返回 None=跳过精排。

降级铁律（spec 边界案例）：rerank 服务不可用 → 上层用融合排序直出并标记 degraded。
服务本体在 W3 全量素材阶段部署（RERANK_BASE_URL 空 = 直通降级路径）。
"""
import logging

import httpx

logger = logging.getLogger(__name__)

_TIMEOUT = 15.0  # 全量语料候选增多 + 与其他 GPU 任务共存时的安全余量


def _http(timeout: float = _TIMEOUT) -> httpx.Client:
    return httpx.Client(timeout=timeout)


def rerank(query: str, documents: list[str], base_url: str | None,
           timeout: float = _TIMEOUT) -> list[float] | None:
    """返回与 documents 等长的分数列表；未配置/空文档/任何异常 → None。"""
    if not base_url or not documents:
        return None
    try:
        with _http(timeout) as cli:
            resp = cli.post(
                f"{base_url.rstrip('/')}/rerank",
                json={"query": query, "documents": documents},
            )
            resp.raise_for_status()
            scores = resp.json().get("scores")
            if isinstance(scores, list) and len(scores) == len(documents):
                return [float(s) for s in scores]
            logger.warning("rerank 响应格式异常: %s", str(resp.json())[:120])
            return None
    except Exception as exc:  # noqa: BLE001 —— 降级边界，绝不抛出
        logger.warning("rerank 调用失败(将跳过精排): %s", exc)
        return None


def health(base_url: str | None) -> bool:
    """服务探活；未配置即 False。"""
    if not base_url:
        return False
    try:
        with _http(2.0) as cli:
            return cli.get(f"{base_url.rstrip('/')}/health").status_code == 200
    except Exception:  # noqa: BLE001 —— 探活失败即不可用
        return False
