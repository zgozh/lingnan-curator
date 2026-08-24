"""meta.csv 解析与版权校验。

版权红线（AGENTS.md 硬约束 1）：license / source_url 缺失的照片禁止入库，
宁缺毋滥。photo_id 必须唯一且对应 raw 目录下的 jpg/png/jpeg 文件。
"""
import csv
from pathlib import Path

from app.models import PhotoRecord

_VALID_EXT = (".jpg", ".jpeg", ".png")


def find_image(raw_dir: Path, photo_id: str) -> Path | None:
    for ext in _VALID_EXT:
        p = raw_dir / f"{photo_id}{ext}"
        if p.exists():
            return p
    return None


def load_meta(csv_path: Path, raw_dir: Path) -> tuple[list[PhotoRecord], list[str]]:
    """返回 (合法记录列表, 错误行列表)。错误行格式 "photo_id: 原因"。"""
    ok: list[PhotoRecord] = []
    errors: list[str] = []
    seen: set[str] = set()

    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        for i, row in enumerate(csv.DictReader(f), start=2):  # 行号含表头
            pid = (row.get("photo_id") or "").strip()
            title = (row.get("title") or "").strip()
            source_url = (row.get("source_url") or "").strip()
            license_ = (row.get("license") or "").strip()

            if not pid:
                errors.append(f"第{i}行: photo_id 缺失")
                continue
            if not title:
                errors.append(f"{pid}: title 缺失")
                continue
            if not license_:
                errors.append(f"{pid}: license 缺失(版权红线,拒绝入库)")
                continue
            if not source_url:
                errors.append(f"{pid}: source_url 缺失(版权红线,拒绝入库)")
                continue
            if pid in seen:
                errors.append(f"{pid}: photo_id 重复")
                continue
            if find_image(raw_dir, pid) is None:
                errors.append(f"{pid}: raw 目录找不到 jpg/png/jpeg 文件")
                continue

            seen.add(pid)
            ok.append(
                PhotoRecord(
                    photo_id=pid,
                    title=title,
                    year=(row.get("year") or "").strip(),
                    location=(row.get("location") or "").strip(),
                    source_url=source_url,
                    license=license_,
                )
            )
    return ok, errors
