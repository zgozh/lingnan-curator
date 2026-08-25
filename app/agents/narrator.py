"""F6 讲解员口播：photo_id → 馆藏著录 → 粤语白话讲解词 → TTS 音频。

降级语义：TTS 失败 → narrate 返回 audio=False + degraded=True，
详情页隐藏播放入口（spec 边界案例）。
"""
import logging
from pathlib import Path

from app.infra import llm_client as lc
from app.infra.tts import get_tts
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)

_SYSTEM = (
    "你是岭南老照片展馆的粤语讲解员。依据【馆藏著录】写一段 <=200 字的"
    "粤语白话讲解词，开头用「各位观众」；只用著录里的事实，"
    '输出严格 JSON：{"script": "..."}。'
)


def _hit(photo_id: str, settings=None):
    """seam：按 photo_id 取馆藏著录。"""
    from app.config import Settings

    s = settings or Settings.load()
    from app.infra.milvus_store import get_client

    rows = get_client(s).query(
        collection_name=s.collection,
        filter=f'photo_id == "{photo_id}"',
        output_fields=["title", "year", "location", "caption"],
        limit=1,
    )
    return rows[0] if rows else None


def _out_dir(photo_id: str) -> Path:
    return Path("data/processed") / photo_id


def _f(row, key: str) -> str:
    """dict / 对象两种著录形态的统一取值。"""
    if isinstance(row, dict):
        return row.get(key) or ""
    return getattr(row, key, "") or ""


def write_script(photo_id: str, settings=None) -> str:
    row = _hit(photo_id, settings)
    if not row:
        raise LookupError(f"馆藏中不存在 photo_id={photo_id}")
    desc = (f"《{_f(row, 'title')}》"
            f"{'（' + _f(row, 'year') + '）' if _f(row, 'year') else ''}"
            f"{'·' + _f(row, 'location') if _f(row, 'location') else ''}"
            f"｜{_f(row, 'caption')}")
    raw = lc.chat([{"role": "system", "content": _SYSTEM},
                   {"role": "user", "content": f"【馆藏著录】{desc}"}],
                  json_mode=True, settings=settings)
    obj = extract_json(raw) or {}
    script = str(obj.get("script") or "").strip()
    if not script:
        raise ValueError("讲解词生成失败")
    return script


def _tts(settings=None):
    """seam：测试替换 TTS 提供方。"""
    return get_tts(settings)


def narrate(photo_id: str, settings=None) -> dict:
    """生成讲解词并合成音频；返回 {audio: bool, degraded: bool, ...}。"""
    s = settings or __import__("app.config",
                               fromlist=["Settings"]).Settings.load()
    out_dir = _out_dir(photo_id)
    result: dict = {"photo_id": photo_id, "audio": False, "degraded": False}
    try:
        script = write_script(photo_id, s)
    except (LookupError, ValueError) as exc:
        logger.warning("narrate 跳过: %s", exc)
        result["error"] = str(exc)
        result["degraded"] = True
        return result
    result["script"] = script
    voice = s.tts_voice
    ok = _tts(s).synthesize(script, voice, out_dir / "narration.wav")
    result["audio"] = ok
    result["voice"] = voice
    result["degraded"] = not ok
    return result
