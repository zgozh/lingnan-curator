"""F1 入库管线编排：修复→上色→OCR→描述→向量化→入库。

降级铁律落地：任一步失败记 StepResult 继续，单张缺文件跳过不中断整批，
报告 UTF-8 落盘（spec 边界案例）。
"""
import logging
from datetime import datetime, timezone
from pathlib import Path

from app.config import Settings
from app.infra.embedder import Embedder
from app.infra.milvus_store import ensure_collection, get_client, upsert_photo
from app.ingest.caption_op import caption_photo
from app.ingest.meta import find_image
from app.ingest.ocr_op import run_ocr
from app.ingest.vision_ops import colorize, restore_face
from app.models import IngestReport, PhotoRecord, StepStatus

logger = logging.getLogger(__name__)


def _get_embedder() -> Embedder:
    return Embedder()


def _add(report: IngestReport, step: str, ok: bool, ok_detail: str = "",
         degraded_detail: str = "") -> None:
    report.add(step, StepStatus.OK if ok else StepStatus.DEGRADED,
               ok_detail if ok else degraded_detail)


def run_pipeline(
    records: list[PhotoRecord],
    raw_dir: Path,
    out_root: Path,
    report_path: Path,
) -> IngestReport:
    settings = Settings.load()
    report = IngestReport(
        started_at=datetime.now(timezone.utc).isoformat(timespec="seconds")
    )
    client = get_client(settings)
    ensure_collection(client, settings.collection)  # 幂等建表
    emb = _get_embedder()

    try:
        for rec in records:
            src = find_image(Path(raw_dir), rec.photo_id)
            if src is None:
                report.add(f"{rec.photo_id}/locate", StepStatus.FAILED,
                           "raw 目录缺文件，跳过该照片")
                continue
            dst = Path(out_root) / rec.photo_id
            dst.mkdir(parents=True, exist_ok=True)

            # 1 修复（挂 → 用原图继续）
            ok = restore_face(src, dst / "restored.jpg")
            rec.restored = ok
            base = dst / "restored.jpg" if ok else src
            _add(report, f"{rec.photo_id}/restore", ok,
                 "", "修复失败，改用原图继续")

            # 2 上色（挂 → 用修复图继续）
            okc = colorize(base, dst / "colorized.jpg")
            rec.colorized = okc
            work = dst / "colorized.jpg" if okc else base
            _add(report, f"{rec.photo_id}/colorize", okc,
                 "", "上色失败，改用修复图继续")

            # 3 OCR（空结果=DEGRADED；引擎异常=FAILED 但不中断）
            try:
                txt = run_ocr(work)
                rec.ocr_text = txt or ""
                _add(report, f"{rec.photo_id}/ocr", bool(txt),
                     "", "OCR 空结果（纯画面照属正常）")
            except Exception as exc:  # noqa: BLE001 —— 降级边界
                rec.ocr_text = ""
                report.add(f"{rec.photo_id}/ocr", StepStatus.FAILED, str(exc)[:200])

            # 4 caption（caption_photo 内部已兜底为 fallback 拼接）
            cap = caption_photo(work, rec)
            rec.caption, rec.tags = cap.description, cap.tags
            _add(report, f"{rec.photo_id}/caption", cap.model != "fallback",
                 cap.model, f"VLM 降级({cap.model})")

            # 5 向量化 + 幂等入库（文本索引=title+元数据+caption+ocr 拼接）
            try:
                text_for_index = " ".join(
                    x for x in [rec.title, rec.year, rec.location,
                                rec.caption, rec.ocr_text] if x
                )
                dense, sparse = emb.texts(text_for_index)
                clip = emb.image(work)
                upsert_photo(client, rec, dense=dense, sparse=sparse,
                             clip=clip, collection=settings.collection)
                report.add(f"{rec.photo_id}/store", StepStatus.OK)
            except Exception as exc:  # noqa: BLE001 —— 单张存储失败不拖垮批次
                logger.exception("store 失败 %s", rec.photo_id)
                report.add(f"{rec.photo_id}/store", StepStatus.FAILED, str(exc)[:200])
    finally:
        emb.free()  # 显存纪律：阶段结束释放
        report.finished_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
        Path(report_path).parent.mkdir(parents=True, exist_ok=True)
        Path(report_path).write_text(report.to_json(), encoding="utf-8")

    return report
