"""F5 文创 Agent：photo_id + 类型 → 结构化文案 JSON（明信片/slogan/朋友圈）。"""
import logging
from typing import Any

from app.infra import llm_client as lc
from app.retrieval import pipeline as rpipe
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)

_TYPES: dict[str, str] = {
    # type → 文创形态说明（进提示词）
    "postcard": "明信片：正面配馆藏老照片，背面写 <=60 字的怀旧寄语",
    "slogan": "展览 slogan：<=16 字，朗朗上口",
    "moments": "朋友圈文案：<=80 字，带话题标签 2 个",
}


class _Hit:
    """轻量只读视图，供提示词组装。"""

    def __init__(self, hit):
        self.photo_id = hit.photo_id
        self.title = hit.title
        self.year = hit.year
        self.location = hit.location
        self.caption = hit.caption


def _hit(photo_id: str, settings=None) -> _Hit | None:
    """seam：按 photo_id 精确取馆藏著录。"""
    try:
        from app.infra.milvus_store import get_client

        rows = get_client(settings).query(
            collection_name=(settings or __import__(
                "app.config", fromlist=["Settings"]).Settings.load()).collection,
            filter=f'photo_id == "{photo_id}"',
            output_fields=["title", "year", "location", "caption"],
            limit=1,
        )
        row = rows[0] if rows else None
        return _Hit(type("H", (), {"photo_id": photo_id, **row})) if row else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("文创取著录失败: %s", exc)
        return None


def create(photo_id: str, copy_type: str, settings=None) -> dict[str, Any]:
    if copy_type not in _TYPES:
        raise ValueError(f"不支持的文创类型: {copy_type}，"
                         f"可选: {sorted(_TYPES)}")
    hit = _hit(photo_id, settings)
    if hit is None:
        raise LookupError(f"馆藏中不存在 photo_id={photo_id}")

    desc = (f"《{hit.title}》"
            f"{'（' + hit.year + '）' if hit.year else ''}"
            f"{'·' + hit.location if hit.location else ''}｜{hit.caption}")
    system = (
        f"你是岭南老照片文创写手。任务：{_TYPES[copy_type]}。"
        '输出严格 JSON：{"title": "<=20字标题", "body": "正文"}。'
        "基于馆藏著录创作，不得虚构史实；简体中文。"
    )
    raw = lc.chat([{"role": "system", "content": system},
                   {"role": "user", "content": f"【馆藏著录】{desc}"}],
                  json_mode=True, settings=settings)
    obj = extract_json(raw) or {}
    return {"photo_id": photo_id, "type": copy_type,
            "copy": {"title": str(obj.get("title") or "").strip(),
                     "body": str(obj.get("body") or "").strip()}}
