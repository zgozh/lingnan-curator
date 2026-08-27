"""实验4：按照片内容定制上色提示词（利用已有 caption 元数据）。

对比三路输出：本地 DDColor 原版 / 存档批量版(通用模板) / 定制提示词 E2。
指标：R-B 偏色、饱和度、与 restored 的结构保持度。
产物 data/processed/{pid}/compare4/。
"""
import json
import logging
from pathlib import Path

from PIL import Image

logging.basicConfig(level=logging.INFO, format="%(message)s")

PID = "gz_filegodownsinhonamjp_031"      # Godowns in Honam 1857 (黄白代表)
ROOT = Path("data/processed") / PID
OUT = ROOT / "compare4"
OUT.mkdir(parents=True, exist_ok=True)

PROMPT_SYSTEM = (
    "你是老照片上色的色彩指导。给你一张历史照片的AI著录描述，"
    "请输出一段中文上色提示词（80字内），只描述这张照片里该有的具体颜色："
    "天空/水面/建筑材质/衣物/肤色的合理自然色调。"
    "要求贴近史实、自然不鲜艳过度、明确避免整体泛黄泛棕。"
    '输出严格 JSON：{"prompt": "..."}')


def metrics(im: Image.Image) -> str:
    small = im.convert("RGB").resize((640, 344))
    px = small.split()
    n = small.size[0] * small.size[1]
    means = [sum(c.getdata()) / n for c in px]
    hsv = small.convert("HSV")
    sat = sum(hsv.split()[1].getdata()) / n / 255 * 100
    return f"R={means[0]:.0f} G={means[1]:.0f} B={means[2]:.0f} " \
           f"R-B={means[0]-means[2]:+.0f} 饱和={sat:.1f}%"


def y_corr(a: Image.Image, b: Image.Image) -> float:
    ay = a.convert("YCbCr").split()[0].resize((512, 274))
    by = b.convert("YCbCr").split()[0].resize((512, 274))
    da = list(ay.getdata())
    db = list(by.getdata())
    n = len(da)
    ma, mb = sum(da) / n, sum(db) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(da, db)) / n
    va = (sum((x - ma) ** 2 for x in da) / n) ** .5
    vb = (sum((y - mb) ** 2 for y in db) / n) ** .5
    return cov / (va * vb) if va and vb else 0.0


def main() -> None:
    from app.config import Settings
    from app.infra import llm_client as lc
    from app.infra.milvus_store import get_client
    from app.ingest.cloud_refine import refine_image

    s = Settings.load()
    row = get_client(s).query(
        collection_name=s.collection,
        filter=f'photo_id == "{PID}"',
        output_fields=["title", "year", "location", "caption"], limit=1)[0]
    ctx = (f"标题：{row.get('title')}；年代：{row.get('year')}；"
           f"地点：{row.get('location')}；描述：{row.get('caption')}")
    logging.info("著录上下文: %s", ctx[:120])
    raw = lc.chat([{"role": "system", "content": PROMPT_SYSTEM},
                   {"role": "user", "content": ctx}],
                  json_mode=True, model=s.review_model, settings=s)
    from app.utils.json_utils import extract_json
    prompt = (extract_json(raw) or {}).get("prompt") or ""
    if not prompt:
        print("[NG] 提示词生成失败")
        return
    logging.info("定制提示词: %s", prompt)
    (OUT / "tailored-prompt.txt").write_text(prompt, encoding="utf-8")

    ref = Image.open(ROOT / "restored.jpg").convert("RGB")
    small = ref.copy()
    small.thumbnail((1440, 1440), Image.LANCZOS)
    tin = OUT / ".in.jpg"
    small.save(tin, quality=92)
    ok = refine_image(tin, OUT / ".c.png", function="colorization",
                      prompt=prompt, settings=s)
    tin.unlink(missing_ok=True)
    if not ok:
        print("[NG] 云端上色失败")
        return
    cloud = Image.open(OUT / ".c.png").convert("RGB")
    cloud_r = cloud.resize(ref.size, Image.LANCZOS) if \
        cloud.size != ref.size else cloud
    # E2 合成：Y 取本地
    y = ref.convert("YCbCr").split()[0]
    cb, cr = cloud_r.convert("YCbCr").split()[1:]
    comp = Image.merge("YCbCr", (y, cb, cr)).convert("RGB")
    tw = 3200
    comp = comp.resize((tw, int(comp.size[1] * tw / comp.size[0])),
                       Image.LANCZOS)
    comp.save(OUT / "v-tailored.jpg", quality=93)
    (OUT / ".c.png").unlink(missing_ok=True)

    print("\n=== 指标对比 ===")
    print("原DDColor :", metrics(Image.open(ROOT / "colorized.jpg")))
    arch = ROOT / "enhanced-archive" / f"enhanced-{PID}.jpg"
    if arch.exists():
        print("批量存档版:", metrics(Image.open(arch)))
    print("定制E2   :", metrics(comp))
    print(f"结构保持度(vs restored): {y_corr(ref.resize(comp.size), comp):.3f}")


if __name__ == "__main__":
    main()
