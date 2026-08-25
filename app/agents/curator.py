"""F3 策展人 Agent：主题词 → 检索取池 → 展览编排 JSON（章节/选图/串场词）。"""
import logging

from app.infra import llm_client as lc
from app.retrieval import pipeline as rpipe
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)

_SYSTEM = (
    "你是岭南老照片展馆的策展人。依据【候选照片池】为给定主题编排专题展，"
    '输出严格 JSON：{"sections": [{"title": "<=12字", "narrative": "<=80字串场词",'
    ' "photo_ids": ["从候选池选择"]}]}，2~3 个章节；'
    "photo_ids 只能来自候选池；使用简体中文。"
)


def compose(theme: str, settings=None) -> dict:
    res = rpipe.search(theme, top_k=12)
    hits = res.hits
    if not hits:
        return {"theme": theme, "sections": [], "refused": True,
                "degraded": sorted(res.degraded)}

    pool = "\n".join(
        f"- {h.photo_id}｜《{h.title}》｜{h.caption}" for h in hits
    )
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": f"【主题】{theme}\n【候选照片池】\n{pool}"},
    ]
    try:
        raw = lc.chat(messages, json_mode=True, settings=settings)
    except Exception as exc:  # noqa: BLE001 —— LLM 失败降级为线性陈列
        logger.warning("curator LLM 失败，降级单章陈列: %s", exc)
        return {"theme": theme, "refused": False,
                "degraded": sorted(set(res.degraded) | {"llm"}),
                "sections": [{"title": theme, "narrative": "",
                              "photo_ids": [h.photo_id for h in hits]}]}

    obj = extract_json(raw) or {}
    valid = {h.photo_id for h in hits}
    sections = []
    for sec in obj.get("sections") or []:
        ids = [p for p in (sec.get("photo_ids") or []) if p in valid]
        if ids:
            sections.append({"title": str(sec.get("title") or "")[:24],
                             "narrative": str(sec.get("narrative") or ""),
                             "photo_ids": ids})
    return {"theme": theme, "sections": sections, "refused": not sections,
            "degraded": sorted(res.degraded)}
