"""Agent① 照片洞察：VLM 看图 → 结构化 Insight。

降级铁律：VLM 调用或 JSON 解析任何一步失败，都返回基于元数据的
degraded Insight（source="metadata"），绝不向上抛异常、不打垮叙事链。
"""
from pathlib import Path

from app.infra import llm_client as lc
from app.narrator.prompts import INSIGHT_SYSTEM
from app.narrator.types import Character, Insight
from app.utils.json_utils import extract_json

_CHARACTER_FIELDS = ("who", "clothing", "age_hint")


def _str_list(value) -> list[str]:
    """把 VLM 返回的任意值规整成 str list；非 list 返回空。"""
    if not isinstance(value, list):
        return []
    return [str(x) for x in value if x is not None]


def _metadata_insight(meta_desc: str) -> Insight:
    """降级路径：只用元数据拼接 scene，其余字段留空。"""
    return Insight(
        scene=(meta_desc or "一张岭南老照片").strip(),
        source="metadata",
        degraded=True,
    )


def insight(image_path, metadata_desc, settings=None, vlm=None) -> Insight:
    v = vlm if vlm is not None else lc.get_vlm(settings)
    try:
        raw = v.describe(
            Path(image_path),
            user_prompt=(
                "请仔细观察这张老照片，按 system 要求输出严格 JSON。"
                f"已知元数据：{metadata_desc or '无'}"
            ),
            system_prompt=INSIGHT_SYSTEM,
            json_mode=True,
        )
        data = extract_json(raw)
        if not data:
            return _metadata_insight(metadata_desc)
        return Insight(
            scene=str(data.get("scene") or "").strip(),
            visibles=_str_list(data.get("visibles")),
            characters=[
                Character(**{k: str(c.get(k) or "") for k in _CHARACTER_FIELDS})
                for c in data.get("characters") or []
                if isinstance(c, dict)
            ],
            era_evidence=_str_list(data.get("era_evidence")),
            maybe_place=str(data.get("maybe_place") or "不确定").strip(),
            mood=str(data.get("mood") or "").strip(),
            confident_words=str(data.get("confident_words") or "").strip(),
            source="vlm",
            degraded=False,
        )
    except Exception:
        return _metadata_insight(metadata_desc)