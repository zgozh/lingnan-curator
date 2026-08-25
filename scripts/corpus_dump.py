"""语料库检视/导出小工具（开发辅助，不属主链路）。

用法：
  uv run python scripts/corpus_dump.py                 # 打印全部实体摘要
  uv run python scripts/corpus_dump.py --out eval/corpus.jsonl
  uv run python scripts/corpus_dump.py --purge id1,id2 # 按 pk 删除(维护用)
"""
import argparse
import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    from app.config import Settings
    from app.infra.milvus_store import get_client

    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    ap.add_argument("--purge", default="",
                    help="逗号分隔 photo_id，删除后退出")
    args = ap.parse_args()

    s = Settings.load()
    client = get_client(s)
    fields = ["photo_id", "title", "year", "location", "caption"]

    if args.purge:
        pks = [p.strip() for p in args.purge.split(",") if p.strip()]
        client.delete(collection_name=s.collection, pks=pks)
        client.flush(collection_name=s.collection)
        print(f"[OK] 已删除 {len(pks)} 个 pk 并 flush")

    rows = client.query(collection_name=s.collection,
                        filter='photo_id != ""',
                        output_fields=fields, limit=500,
                        consistency_level="Strong")
    rows.sort(key=lambda r: r["photo_id"])
    print(f"=== 共 {len(rows)} 个实体 ===")
    for r in rows:
        cap = (r.get("caption") or "")[:60]
        print(f"{r['photo_id']:<28} {r.get('year') or '----':<6}"
              f" 《{(r.get('title') or '')[:36]}》 {cap}")

    if args.out:
        out = ROOT / args.out
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            "\n".join(json.dumps(r, ensure_ascii=False) for r in rows),
            encoding="utf-8")
        print(f"[OK] 已写出 {out}")


if __name__ == "__main__":
    main()
