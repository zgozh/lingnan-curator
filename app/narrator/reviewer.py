"""Agent④ 故事一致性审稿：Insight + Story → 0-100 分 ReviewResult。

对照照片洞察审查故事的事实一致性 / AI 腔文本质量 / 情感与年代贴合度。
降级铁律：审稿 LLM 调用异常 → ReviewResult(score=100, issues=[], suggestion="")
（跳过审稿、视为通过），绝不向上抛异常、不打垮叙事链（T9 用它决定是否回炉重写）。
"""
import logging

from app.config import Settings
from app.infra import llm_client as lc
from app.narrator.prompts import REVIEW_SYSTEM
from app.narrator.types import Insight, ReviewResult, Story
from app.utils.json_utils import extract_json

logger = logging.getLogger(__name__)


def review(insight: Insight, story: Story, settings: Settings | None = None,
           chat=None) -> ReviewResult:
    """对照照片洞察审查故事，返回 0-100 分 ReviewResult。

    chat 缺省 lc.chat；审稿固定 json_mode=True、temperature=0.2、model=s.review_model。
    任何异常 → ReviewResult(score=100, issues=[], suggestion="")（跳过审稿）。
    """
    s = settings or Settings.load()
    call = chat if chat is not None else lc.chat
    try:
        user = (
            "【照片洞察】"
            f"scene={insight.scene}｜visibles={insight.visibles}｜"
            f"place={insight.maybe_place}｜mood={insight.mood}\n"
            f"【故事】{story.text}"
        )
        raw = call(
            [{"role": "system", "content": REVIEW_SYSTEM},
             {"role": "user", "content": user}],
            json_mode=True, temperature=0.2, model=s.review_model, settings=s,
        )
        obj = extract_json(raw) or {}
        score = obj.get("score")
        score = int(score) if isinstance(score, (int, float)) else 0
        return ReviewResult(
            score=score,
            issues=[str(x) for x in obj.get("issues", [])],
            suggestion=str(obj.get("suggestion") or ""),
        )
    except Exception:
        logger.warning("review LLM 调用失败，跳过审稿（视为通过）", exc_info=True)
        return ReviewResult(score=100, issues=[], suggestion="")