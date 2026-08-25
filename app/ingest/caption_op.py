"""caption 节点：VLM 生成图片描述与标签；任何失败降级为标题+元数据拼接。"""
import json
import logging
from dataclasses import dataclass
from pathlib import Path

from app.infra.llm_client import CAPTION_SYSTEM, DashScopeVLM, get_vlm
from app.models import PhotoRecord

logger = logging.getLogger(__name__)


@dataclass
class Caption:
    description: str
    tags: list[str]
    model: str


def fallback_caption(record: PhotoRecord) -> Caption:
    """spec 边界案例：VLM 挂 → 标题+元数据拼接，管线不中断。"""
    bits = [record.title]
    if record.year:
        bits.append(f"约{record.year}年")
    if record.location:
        bits.append(record.location)
    return Caption(description="，".join(bits), tags=[], model="fallback")


def extract_json(text: str) -> dict | None:
    """兼容壳：公共实现已上移 app.utils.json_utils。"""
    from app.utils.json_utils import extract_json as _impl

    obj = _impl(text)
    return obj if isinstance(obj, dict) else None


def caption_photo(
    image_path: Path,
    record: PhotoRecord,
    client: DashScopeVLM | None = None,
) -> Caption:
    prompt = f"{CAPTION_SYSTEM}\n已知元数据：标题={record.title}；年代={record.year or '不详'}；地点={record.location or '不详'}"
    try:
        client = client or get_vlm()
        raw = client.describe(image_path, prompt)
    except Exception as exc:  # noqa: BLE001 —— 降级边界（含无 key 构造失败）
        logger.warning("VLM 调用失败(%s)，降级拼接: %s", record.photo_id, exc)
        return fallback_caption(record)

    obj = extract_json(raw)
    desc = (obj or {}).get("description")
    tags_raw = (obj or {}).get("tags", [])
    if not isinstance(desc, str) or not desc.strip():
        logger.warning("VLM 输出缺 description(%s)，降级拼接", record.photo_id)
        return fallback_caption(record)
    tags = [str(t) for t in tags_raw][:8] if isinstance(tags_raw, list) else []
    return Caption(description=desc.strip(), tags=tags, model="qwen-vl")
