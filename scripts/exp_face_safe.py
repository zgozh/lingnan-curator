"""实验3：不改脸的两条替代链验证（针对 v1 幻改人脸问题）。

- E1 direct : restored → 预缩 → 万相 colorization(自然色提示词) → 回贴锐化
              （上色模型非自由重绘，结构漂移应远小于 description_edit）
- E2 composite : E1 结果仅取色度(CbCr)，亮度(Y)完全用本地 restored
              —— 像素级保证脸/褶皱结构与本地一致，只借颜色

指标：各变体 Y 通道与 restored 的归一化互相关(>0.9 视为结构未动)。
产物 data/processed/{pid}/compare3/。
"""
import logging
from pathlib import Path

from PIL import Image, ImageFilter

logging.basicConfig(level=logging.INFO, format="%(message)s")
PID = "gz_file1919jpg_006"
ROOT = Path("data/processed") / PID
OUT = ROOT / "compare3"
OUT.mkdir(parents=True, exist_ok=True)

IN_LONG = 1440
OUT_W = 3200
COLOR_PROMPT = (
    "为这张黑白老照片上自然真实的现代色彩：真实亚洲人健康肤色、"
    "蓝天白云、深蓝或黑色西装、白色衬衫、草木绿色、建筑物呈现灰白原色；"
    "色调均衡不过度偏黄偏棕，不要做旧泛黄的怀旧滤镜，颜色自然鲜艳")


def _y_corr(a: Image.Image, b: Image.Image) -> float:
    """两图 Y 通道归一化互相关（结构相似度粗代理）。"""
    ay = a.convert("YCbCr").split()[0].resize((512, 274))
    by = b.convert("YCbCr").split()[0].resize((512, 274))
    da = list(ay.get_flattened_data() if hasattr(ay, "get_flattened_data")
              else ay.getdata())
    db = list(by.get_flattened_data() if hasattr(by, "get_flattened_data")
              else by.getdata())
    n = len(da)
    ma, mb = sum(da) / n, sum(db) / n
    cov = sum((x - ma) * (y - mb) for x, y in zip(da, db)) / n
    va = (sum((x - ma) ** 2 for x in da) / n) ** .5
    vb = (sum((y - mb) ** 2 for y in db) / n) ** .5
    return cov / (va * vb) if va and vb else 0.0


def main():
    from app.config import Settings
    from app.ingest.cloud_refine import refine_image

    s = Settings.load()
    base = Image.open(ROOT / "restored.jpg").convert("RGB")
    small_in = OUT / ".in.jpg"
    im = base.copy()
    im.thumbnail((IN_LONG, IN_LONG), Image.LANCZOS)
    im.save(small_in, quality=92)
    ok = refine_image(small_in, OUT / ".color.png",
                      function="colorization", prompt=COLOR_PROMPT,
                      settings=s)
    small_in.unlink(missing_ok=True)
    if not ok:
        print("[NG] colorization 失败，退出")
        return
    cloud = Image.open(OUT / ".color.png").convert("RGB")

    def up(im2):
        w, h = im2.size
        tw = max(OUT_W, w)
        r = im2.resize((tw, int(h * tw / w)), Image.LANCZOS)
        return r.filter(ImageFilter.UnsharpMask(radius=2.2, percent=80,
                                                threshold=3))

    e1 = up(cloud)
    e1.save(OUT / "e1-direct.jpg", quality=93)

    # E2: Y 取自本地 restated、CbCr 取自云端
    ref = Image.open(ROOT / "restored.jpg").convert("RGB")
    ref_r = ref.resize(e1.size, Image.LANCZOS)
    y = ref_r.convert("YCbCr").split()[0]
    cb, cr = e1.convert("YCbCr").split()[1:]
    e2 = Image.merge("YCbCr", (y, cb, cr)).convert("RGB")
    e2.save(OUT / "e2-composite.jpg", quality=93)
    (OUT / ".color.png").unlink(missing_ok=True)

    # 指标：结构保持度（v1 作对照）
    out_y = Image.new("RGB", e1.size, (120, 120, 120))
    metrics = {"e1-direct": _y_corr(ref_r, e1),
               "e2-composite": _y_corr(ref_r, e2)}
    try:
        v1 = Image.open(ROOT / "enhanced-v1-faceshift.jpg").convert("RGB")
        metrics["v1-faceshift"] = _y_corr(ref_r, v1.resize(e1.size))
        del out_y
    except Exception:  # noqa: BLE001 —— v1 缺席不阻塞
        pass
    for k, v in metrics.items():
        print(f"[OK] 结构保持度 {k}: {v:.3f}")

    # 人脸特写拼图
    from PIL import ImageDraw, ImageFont

    faces = [("restored.jpg", ROOT, "本地基准(restored)"),
             ("colorized.jpg", ROOT, "现展示 DDColor"),
             ("e1-direct.jpg", OUT, "E1 云纯上色"),
             ("e2-composite.jpg", OUT, "E2 只借色不动脸")]
    W = 1150
    crops = []
    for fn, bdir, lab in faces:
        img = Image.open(bdir / fn).convert("RGB")
        w, h = img.size
        c = img.crop((int(w * 0.30), int(h * 0.05), int(w * 0.72),
                      int(h * 0.58)))
        tw = W // 2 - 24
        crops.append((c.resize((tw, int(c.size[1] * tw / c.size[0])),
                               Image.LANCZOS), lab))
    lh, gap = 54, 10
    H = 2 * lh + max(crops[0][0].size[1], crops[1][0].size[1]) + \
        max(crops[2][0].size[1], crops[3][0].size[1]) + gap * 3
    cv = Image.new("RGB", (W, H), "white")
    d = ImageDraw.Draw(cv)
    try:
        font = ImageFont.truetype(r"C:\Windows\Fonts\msyh.ttc", 30)
    except Exception:  # noqa: BLE001
        font = ImageFont.load_default()
    pos = [(0, 0), (W // 2, 0), (0, lh + max(crops[0][0].size[1],
           crops[1][0].size[1]) + gap), (W // 2, lh + max(crops[0][0].size[1],
           crops[1][0].size[1]) + gap)]
    for (img, lab), (px, py) in zip(crops, pos):
        d.text((px + 8, py + 8), lab, fill="black", font=font)
        cv.paste(img, (px, py + lh))
    cv.save(OUT / "sheet-faces.png")
    print(f"[OK] 拼图 {OUT/'sheet-faces.png'}")


if __name__ == "__main__":
    main()
