"""e2e 验证：报告统计 + Milvus 数据抽查。"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.infra.milvus_store import count_photos, get_client

r = json.loads(Path("data/processed/_report.json").read_text(encoding="utf-8"))
ok = sum(1 for i in r["items"] if i["status"] == 1)
dg = sum(1 for i in r["items"] if i["status"] == 2)
fail = sum(1 for i in r["items"] if i["status"] == 3)
print(f"report: OK={ok} DEGRADED={dg} FAILED={fail}")

c = get_client()
print("Milvus 照片数:", count_photos(c))
rows = c.query(
    collection_name="lingnan_photos",
    filter='photo_id != ""',
    output_fields=["photo_id", "title", "year", "location", "license"],
    limit=10,
)
for row in rows:
    print(" ", row)
