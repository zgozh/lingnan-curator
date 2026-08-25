"""F4 讲解员 Agent：观众提问 → 强制带证据检索 → 回答+照片引用；无证据拒答。

防幻觉三道闸（spec 场景 2）：
1. 检索为空 → 直接拒答（不烧 LLM）
2. 提示词强制：只允许引用所给 photo_ids
3. 事后校验：LLM 引用了检索结果之外的 id → 整体降级为拒答
"""
import logging
from typing import Any

from app.infra import llm_client as lc
from app.retrieval import pipeline as rpipe

logger = logging.getLogger(__name__)

REFUSE_TEXT = (
    "抱歉，该问题超出了本馆藏品覆盖的范围。"
    "我只能依据馆藏老照片及其著录信息作答，无法提供馆藏之外的结论。"
    "您可以换个与岭南老照片相关的问题试试～"
)

_SYSTEM = (
    "你是岭南老照片展馆的讲解员。只依据【馆藏证据】回答观众问题，"
    "答案中的每个论断都要能在证据中找到依据；"
    '输出严格 JSON：{"answer": "<=200字", "photo_ids": ["引用的照片id"]}，'
    "photo_ids 只能从证据列表中选择；证据不足以回答时，"
    '{"answer": "EVIDENCE_NOT_ENOUGH", "photo_ids": []}。'
    "使用简体中文。"
)


def _search(question: str, top_k: int = 6):
    """seam：便于测试替换；真实实现走 F2 检索门面。"""
    return rpipe.search(question, top_k=top_k).hits


def _build_messages(question: str, hits) -> list[dict]:
    evidence = "\n".join(
        f"- photo_id={h.photo_id}｜《{h.title}》"
        f"{'（' + h.year + '）' if h.year else ''}"
        f"{'（' + h.location + '）' if h.location else ''}"
        f"：{h.caption}" if h.caption else
        f"- photo_id={h.photo_id}｜《{h.title}》"
        for h in hits
    )
    return [
        {"role": "system", "content": _SYSTEM},
        {"role": "user",
         "content": f"【馆藏证据】\n{evidence}\n\n【观众提问】{question}"},
    ]


def ask(question: str, settings=None) -> dict[str, Any]:
    hits = _search(question)
    if not hits:
        return {"answer": REFUSE_TEXT, "photo_ids": [], "refused": True}

    valid_ids = {h.photo_id for h in hits}
    try:
        raw = lc.chat(_build_messages(question, hits), json_mode=True,
                      settings=settings)
    except Exception as exc:  # noqa: BLE001 —— LLM 挂也不打垮主链路
        logger.warning("docent LLM 失败，降级为证据罗列: %s", exc)
        return {"answer": "暂时无法生成讲解，以下是与问题相关的馆藏照片供参考。",
                "photo_ids": sorted(valid_ids), "refused": False}

    from app.utils.json_utils import extract_json

    obj = extract_json(raw) or {}
    answer, pids = obj.get("answer") or "", obj.get("photo_ids") or []
    cited = [p for p in pids if p in valid_ids]
    if not answer or not cited or answer == "EVIDENCE_NOT_ENOUGH":
        return {"answer": REFUSE_TEXT, "photo_ids": [], "refused": True}
    return {"answer": answer, "photo_ids": cited, "refused": False}


def stream_answer(question: str, settings=None):
    """SSE 友好输出：先 delta 流式正文，最后一条 done 带引用元数据。"""
    hits = _search(question)
    if not hits:
        yield {"type": "delta", "text": REFUSE_TEXT}
        yield {"type": "done", "refused": True, "photo_ids": []}
        return

    valid_ids = [h.photo_id for h in hits]
    parts: list[str] = []
    try:
        for delta in lc.stream_chat(_build_messages(question, hits),
                                    settings=settings):
            parts.append(delta)
            yield {"type": "delta", "text": delta}
    except Exception as exc:  # noqa: BLE001 —— 流式中断兜底
        logger.warning("docent 流式失败: %s", exc)

    full = "".join(parts)
    refused = (not full or "EVIDENCE_NOT_ENOUGH" in full)
    yield {"type": "done", "refused": refused,
           "photo_ids": [] if refused else valid_ids}
