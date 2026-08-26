"""叙事链 Agent 间传递的结构化类型（纯 dataclass，不触网、不 import 外部 SDK）。"""

from dataclasses import dataclass, field


@dataclass
class Character:
    who: str = ""
    clothing: str = ""
    age_hint: str = ""


@dataclass
class Insight:
    scene: str = ""
    visibles: list[str] = field(default_factory=list)
    characters: list[Character] = field(default_factory=list)
    era_evidence: list[str] = field(default_factory=list)
    maybe_place: str = "不确定"
    mood: str = ""
    confident_words: str = ""
    source: str = "vlm"          # vlm | metadata
    degraded: bool = False


@dataclass
class Story:
    text: str = ""
    source: str = "llm"          # llm | fallback_docent
    degraded: bool = False


@dataclass
class NarrationLine:
    text: str = ""
    emotion: str = "平静"


@dataclass
class Narration:
    lines: list[NarrationLine] = field(default_factory=list)


@dataclass
class ReviewResult:
    score: int = 0
    issues: list[str] = field(default_factory=list)
    suggestion: str = ""