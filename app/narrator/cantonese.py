"""Agent③ 粤语旁白生成：Story → 5-7 句粤语分句 + 情绪标注（供 TTS 合成）。

降级铁律：LLM 调用失败或解析异常 → 返回单句兜底 Narration，
绝不向上抛异常、不打垮叙事链（T9 编排直接消费返回值）。
"""
import logging

from app.config import Settings
from app.infra import llm_client as lc
from app.narrator import detox as d
from app.narrator.prompts import NARRATION_SYSTEM
from app.narrator.types import Narration, NarrationLine, Story
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)

_PAD_TEXT = "呢段记忆，仲喺度。"
_PAD_EMOTION = "回味"
_FALLBACK_TEXT = "呢段老广州记忆，好珍贵。"
_FALLBACK_EMOTION = "怀念"


def _normalize(lines_raw) -> list[NarrationLine]:
    """清洗 LLM 返回：跳过非 dict/空文本，情绪不在白名单则回落「平静」。"""
    out: list[NarrationLine] = []
    if not isinstance(lines_raw, list):
        return out
    for item in lines_raw:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text") or "").strip()
        if not text:
            continue
        emo = str(item.get("emotion") or "平静")
        if emo not in d.NARRATION_EMOTIONS:
            emo = "平静"
        out.append(NarrationLine(text=text, emotion=emo))
    return out


def write_narration(story: Story, settings=None, chat=None) -> Narration:
    """把 Story 改写成 5-7 句粤语旁白（每句带情绪），temp 0.7，供 TTS。

    chat 缺省 lc.chat；任何异常 → 单句兜底 Narration，绝不抛异常。
    """
    s = settings or Settings.load()
    call = chat if chat is not None else lc.chat
    try:
        raw = call(
            [
                {"role": "system", "content": NARRATION_SYSTEM},
                {"role": "user", "content": f"【故事】{story.text}"},
            ],
            json_mode=True,
            temperature=0.7,
            model=s.narration_model,
            settings=s,
        )
        obj = extract_json(raw) or {}
        lines = _normalize(obj.get("lines"))
        if len(lines) > 7:
            lines = lines[:7]
        while len(lines) < 5:
            lines.append(NarrationLine(text=_PAD_TEXT, emotion=_PAD_EMOTION))
        return Narration(lines=lines)
    except Exception:
        logger.warning("narration LLM 调用失败，降级为单句兜底", exc_info=True)
        return Narration(lines=[NarrationLine(text=_FALLBACK_TEXT, emotion=_FALLBACK_EMOTION)])