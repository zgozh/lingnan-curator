"""Agent② 情感微故事生成：Insight → LLM 情感微故事 + detox 回炉。

降级铁律：LLM 调用失败或 detox 始终不过 → 返回 degraded Story，
绝不向上抛异常、不打垮叙事链（T9 编排直接消费返回值）。
"""
import logging

from app.config import Settings
from app.infra import llm_client as lc
from app.narrator.detox import validate_story
from app.narrator.prompts import STORY_SYSTEM
from app.narrator.types import Insight, Story

logger = logging.getLogger(__name__)


def _build_messages(insight: Insight) -> list[dict]:
    """system=STORY_SYSTEM；user=【照片洞察】+ insight 关键字段拼接（无 json_mode）。"""
    user_content = (
        "【照片洞察】"
        f"scene={insight.scene}｜visibles={insight.visibles}｜"
        f"characters={insight.characters}｜era={insight.era_evidence}｜"
        f"place={insight.maybe_place}｜mood={insight.mood}｜"
        f"words={insight.confident_words}"
    )
    return [
        {"role": "system", "content": STORY_SYSTEM},
        {"role": "user", "content": user_content},
    ]


def write_story(insight: Insight, settings: Settings | None = None,
                chat=None) -> Story:
    """生成 300-400 字情感微故事；detox 不过则回炉，最多 max_story_retry 次。

    chat 缺省 lc.chat；返回 Story.text 为去首尾空白的正文（raw prose，无标题）。
    """
    s = settings or Settings.load()
    call = chat if chat is not None else lc.chat
    text = ""
    try:
        for attempt in range(s.max_story_retry + 1):
            raw = call(_build_messages(insight), json_mode=False,
                       temperature=0.9, settings=s, model=s.story_model)
            text = (raw or "").strip()
            if not validate_story(text):
                logger.warning("story 第 %d 次未过 detox（过短/命中禁词），回炉重写",
                               attempt + 1)
                continue
            return Story(text=text, source="llm", degraded=False)
    except Exception:
        logger.warning("story LLM 调用失败，降级返回已生成文本", exc_info=True)
    return Story(text=text, source="llm", degraded=True)