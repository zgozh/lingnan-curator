"""抽查馆藏著录（供评测集校准）。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infra.milvus_store import get_client  # noqa: E402

rows = get_client().query(
    collection_name="lingnan_photos",
    filter='photo_id != ""',
    output_fields=["photo_id", "title", "caption", "ocr_text", "year",
                   "location"],
    limit=10,
)
for r in rows:
    print(r["photo_id"], "|", r["title"], "|",
          (r.get("caption") or "")[:60])
