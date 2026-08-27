"""语料快照：Milvus ↔ JSONL 双向搬运，让接收者跳过 GPU 管线直接获得检索能力。

export_snapshot：把线上 collection 全量实体（含三路向量）导出为 JSONL；
load_snapshot：建表（若缺）+ 逐行「先删后插」灌入——与 upsert_photo 同一幂等语义。
sparse 向量在 JSON 中统一以字符串键表示。
"""
import json
import logging
from pathlib import Path

from app.infra.milvus_store import ensure_collection, get_client

logger = logging.getLogger(__name__)

_FIELDS = ["photo_id", "title", "year", "location", "caption", "ocr_text",
           "source_url", "license", "has_colorized",
           "emb_dense", "emb_sparse", "emb_clip"]
DEFAULT_PATH = Path("data/snapshot/corpus.jsonl")


def export_snapshot(client, out_path: Path, collection: str = "lingnan_photos",
                    limit: int = 2000) -> int:
    """导出现有实体；collection 不存在或为空 → 0（不写文件）。"""
    try:
        rows = client.query(collection_name=collection,
                            filter='photo_id != ""',
                            output_fields=_FIELDS, limit=limit)
    except Exception as exc:  # noqa: BLE001 —— 库不可达按 0 处理
        logger.warning("export_snapshot 查询失败: %s", exc)
        return 0
    if not rows:
        return 0
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for r in rows:
            if "emb_sparse" in r and isinstance(r["emb_sparse"], dict):
                r["emb_sparse"] = {str(k): float(v)
                                   for k, v in r["emb_sparse"].items()}
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
            n += 1
    return n


def load_snapshot(client, path: Path,
                  collection: str = "lingnan_photos") -> tuple[int, int]:
    """从 JSONL 灌库：返回 (导入条数, 跳过条数)。先删后插，天然幂等。"""
    path = Path(path)
    if not path.exists():
        logger.warning("load_snapshot 文件不存在: %s", path)
        return 0, 0
    ensure_collection(client, collection)
    added = skipped = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
                pid = str(row.get("photo_id") or "").strip()
                if not pid:
                    skipped += 1
                    continue
                client.delete(collection_name=collection, pks=[pid])
                client.insert(collection_name=collection, data=[row])
                added += 1
            except Exception as exc:  # noqa: BLE001 单行损坏不拖垮导入
                logger.warning("[SKIP] 快照行导入失败: %s", exc)
                skipped += 1
    return added, skipped


def export_default(settings=None) -> int:
    return export_snapshot(get_client(settings), DEFAULT_PATH)


def load_default(settings=None) -> tuple[int, int]:
    return load_snapshot(get_client(settings), DEFAULT_PATH)
