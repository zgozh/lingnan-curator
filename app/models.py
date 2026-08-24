"""核心数据模型：入库记录与批次报告（spec PhotoRecord / IngestReport）。"""
import dataclasses
import json
from dataclasses import dataclass, field
from enum import IntEnum


class StepStatus(IntEnum):
    OK = 1
    DEGRADED = 2
    FAILED = 3


@dataclass
class PhotoRecord:
    """一张照片的元数据 + 管线产物。license/source_url 缺失禁止入库（版权红线）。"""

    photo_id: str
    title: str
    source_url: str
    license: str
    year: str = ""
    location: str = ""
    ocr_text: str = ""
    caption: str = ""
    tags: list[str] = field(default_factory=list)
    restored: bool = False
    colorized: bool = False

    @property
    def has_colorized(self) -> bool:
        return self.colorized


@dataclass
class StepResult:
    step: str
    status: StepStatus
    detail: str = ""


@dataclass
class IngestReport:
    items: list[StepResult] = field(default_factory=list)
    started_at: str = ""
    finished_at: str = ""

    def add(self, step: str, status: StepStatus, detail: str = "") -> None:
        self.items.append(StepResult(step=step, status=status, detail=detail))

    def to_json(self) -> str:
        return json.dumps(
            dataclasses.asdict(self), ensure_ascii=False, indent=2
        )
