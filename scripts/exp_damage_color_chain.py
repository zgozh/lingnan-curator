"""实验2：褶皱平滑 + 真实自然色（针对"黑白上成黄白"问题）。

链路 A（云端两步链，重点验证）：
  restored(灰度高清) --缩到1440--> 万相 description_edit 修褶皱
  --> 万相 colorization 自然色提示词 --> LANCZOS 回贴放大到3840
  --> 轻锐化 --> v-chain.jpg
链路 B（零成本本地去黄）：对现有 DDColor colorized 做灰世界白平衡 → v-dewarm.jpg

产物落 data/processed/{pid}/compare2/。
"""
import logging
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter

logging.basicConfig(level=logging.INFO, format="%(message)s")
PID = "gz_file1919jpg_006"
ROOT = Path("data/processed") / PID
OUT = ROOT / "compare2"
OUT.mkdir(parents=True, exist_ok=True)

TARGET_W = 3840            # 与本地 colorized 同尺寸便于同框对比
CLOUD_IN_W = 1440          # 云输入长边（在接口限制内且别太小丢细节）

REPAIR_PROMPT = (
    "修复这张老照片：去除表面划痕、折痕、褶皱和霉斑污渍，让照片纸面平滑；"
    "严格保持人物面容、姿态、服饰与场景构图完全不变，不添加任何新内容，"
    "保持原有历史质感，输出仍为黑白单色照片")
COLOR_PROMPT = (
    "为这张黑白老照片上自然真实的现代色彩：真实亚洲人健康肤色、"
    "蓝天白云、深蓝或黑色西装、白色衬衫、草木绿色、建筑物呈现灰白原色；"
    "色调均衡不过度偏黄偏棕，不要做旧泛黄的怀旧滤镜，颜色自然鲜艳")


def _shrink(src: Path, dst: Path, long_side: int) -> Path:
    im = Image.open(src).convert("RGB")
    im.thumbnail((long_side, long_side), Image.LANCZOS)
    im.save(dst, quality=92)
    return dst


def _upscale_sharpen(src: Path, dst: Path, target_w: int):
    im = Image.open(src).convert("RGB")
    im = im.resize((target_w, int(im.size[1] * target_w / im.size[0])),
                   Image.LANCZOS)
    im = im.filter(ImageFilter.UnsharpMask(radius=2.2, percent=85,
                                           threshold=3))
    im.save(dst, quality=93)


def chain_a() -> bool:
    from app.config import Settings
    from app.ingest.cloud_refine import refine_image

    s = Settings.load()
    small_in = OUT / ".in-1440.jpg"
    _shrink(ROOT / "restored.jpg", small_in, CLOUD_IN_W)
    ok1 = refine_image(small_in, OUT / ".step1-repair.png",
                       function="description_edit", prompt=REPAIR_PROMPT,
                       settings=s)
    if not ok1:
        return False
    src_for_color = OUT / ".step1-repair.png"
    if Image.open(src_for_color).size[0] < 600:
        return False                                  # 异常小图防御
    ok2 = refine_image(src_for_color, OUT / ".step2-color.png",
                       function="colorization", prompt=COLOR_PROMPT,
                       settings=s)
    if not ok2:
        return False
    _upscale_sharpen(OUT / ".step2-color.png", OUT / "v-chain.jpg", TARGET_W)
    for t in (small_in, OUT / ".step1-repair.png", OUT / ".step2-color.png"):
        t.unlink(missing_ok=True)
    return True


def dewarm_b() -> bool:
    """灰世界白平衡去黄：通道均值拉平 + 轻微提饱和。"""
    im = Image.open(ROOT / "colorized.jpg").convert("RGB")
    px = im.split()
    import functools

    means = [sum(ch.getdata()) / (ch.size[0] * ch.size[1]) for ch in px]
    avg = sum(means) / 3
    gains = [min(avg / m, 1.25) if m > 0 else 1.0 for m in means]
    chans = [ch.point(lambda v, g=g: min(int(v * g), 255))
             for ch, g in zip(px, gains)]
    fixed = Image.merge("RGB", chans)
    fixed = ImageEnhance.Color(fixed).enhance(1.12)
    fixed = ImageEnhance.Sharpness(fixed).enhance(1.3)
    fixed.save(OUT / "v-dewarm.jpg", quality=93)
    return True


if __name__ == "__main__":
    status = {}
    for name, fn in (("chain", chain_a), ("dewarm", dewarm_b)):
        try:
            status[name] = "OK" if fn() else "NG 失败降级"
        except Exception as exc:  # noqa: BLE001 —— 实验脚本允许宽捕获
            status[name] = f"NG {exc}"
        print(f"[{status[name][:2]}] {name}: {status[name]}")
