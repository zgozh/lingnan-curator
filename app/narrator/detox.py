"""确定性"AI 味"拦截器：LLM 无关的常规模板词扫描 + 稿子结构校验。

T6/T9 用 validate_story，T7/T9 用 validate_narration，T12 用 scan_ai_smell
统计禁用词命中。纯逻辑，不触网、不 import 外部 SDK。
"""

from app.narrator.types import NarrationLine

BANNED_TERMS = [
    "在这个世界上", "随着时间", "不禁让人", "是啊", "让我们一起",
    "仿佛时光倒流", "岁月如梭", "时光荏苒", "承载", "勾勒", "见证",
]
NARRATION_EMOTIONS = {"平静", "怀念", "感叹", "温暖", "低啲"}


def scan_ai_smell(text: str) -> list[str]:
    return [t for t in BANNED_TERMS if t in text]


def validate_story(text: str) -> bool:
    if not text or len(text) < 80:
        return False
    return not scan_ai_smell(text)


def validate_narration(lines: list[NarrationLine]) -> bool:
    if not (5 <= len(lines) <= 7):
        return False
    for ln in lines:
        if not (10 <= len(ln.text) <= 20):
            return False
        if ln.emotion not in NARRATION_EMOTIONS:
            return False
    return True