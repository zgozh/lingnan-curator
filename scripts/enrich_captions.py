"""语料增强：用 VLM 对馆藏照片做结构化重描述并回写 caption。

用途：冒烟语料的 caption 太薄导致 RAGAS faithfulness 虚低、讲解员证据不足。
做法：restored.jpg → qwen-vl-plus 结构化著录（主体/人物/环境/文字/年代线索）
     → 按 photo_id 先删后插整行（向量原样保留）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import Settings  # noqa: E402
from app.infra.llm_client import get_vlm  # noqa: E402
from app.infra.milvus_store import get_client  # noqa: E402
from app.utils.json_utils import extract_json  # noqa: E402

FIELDS = ["photo_id", "title", "year", "location", "caption", "ocr_text",
          "source_url", "license", "has_colorized",
          "emb_dense", "emb_sparse", "emb_clip"]

_PROMPT = (
    "你是博物馆藏品著录专家。仔细观察这张岭南老照片，输出一段 120~200 字的"
    "中文著录，依次包含：①画面主体与场景类型；②人物的性别、年龄感、服饰细节"
    "（如西装/长衫/旗袍/戏服/冠饰）与动作神态；③建筑与环境特征"
    "（如骑楼柱廊、招牌、舞台布景、街市）；④可见的文字或标识；"
    "⑤能推断的年代与地域线索。只陈述画面可见事实，不要推测画外信息。"
)


def enrich_one(client, s, pid: str) -> bool:
    rows = client.query(collection_name=s.collection,
                        filter=f'photo_id == "{pid}"',
                        output_fields=FIELDS, limit=1)
    if not rows:
        print(f"[skip] {pid} 不存在")
        return False
    row = dict(rows[0])
    img = Path("data/processed") / pid / "restored.jpg"
    if not img.exists():
        print(f"[skip] {pid} 无底图")
        return False
    vlm = get_vlm(s)
    raw = vlm.describe(str(img), _PROMPT)
    obj = extract_json(raw) or {}
    caption = str(obj.get("description") or "").strip() or raw.strip()
    if not caption or len(caption) < 30:
        print(f"[fail] {pid} 描述过短: {caption!r:.60}")
        return False
    row["caption"] = caption.strip()
    client.delete(collection_name=s.collection,
                  filter=f'photo_id == "{pid}"')
    client.insert(collection_name=s.collection, data=[row])
    print(f"[OK] {pid}: {row['caption'][:50]}…")
    return True


def main() -> None:
    s = Settings.load()
    client = get_client(s)
    pids = sys.argv[1:] or [r["photo_id"] for r in client.query(
        collection_name=s.collection, filter='photo_id != ""',
        output_fields=["photo_id"], limit=50)]
    ok = sum(enrich_one(client, s, p) for p in pids)
    print(f"enriched {ok}/{len(pids)}")


if __name__ == "__main__":
    main()
