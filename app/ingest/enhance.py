"""画质增强云链：褶皱修复 → 自然色上色 → 回贴锐化，产出 enhanced.jpg。

红线：只新增 enhanced.jpg 副产物，绝不覆盖 restored/colorized 原始产物
（历史保真溯源）。任何一步失败返回 False（降级铁律），展示层自动回退
colorized/restored。

分辨率对策（ADR-0011 补充）：万相内部以 ~1400px 档位工作且大图输入会
被缩小，因此这里主动把输入预缩到 IN_LONG_SIDE 再送云端；结果用 LANCZOS
放大回 OUT_LONG_WIDTH 后轻锐化。网页/明信片输出足够，追求极限细节的
场景仍建议参考本地图 v-cf05(7680)。
"""
import logging
from pathlib import Path

from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

IN_LONG_SIDE = 1440        # 云端输入长边（接口限制内、保留可辨细节）
OUT_LONG_WIDTH = 3200      # 回贴目标宽（≥网页展示与明信片 300dpi 需求）

REPAIR_PROMPT = (
    "修复这张老照片：去除表面划痕、折痕、褶皱和霉斑污渍，让照片纸面平滑；"
    "严格保持人物面容、姿态、服饰与场景构图完全不变，不添加任何新内容，"
    "保持原有历史质感，输出仍为黑白单色照片")
COLOR_PROMPT = (
    "为这张黑白老照片上自然真实的现代色彩：真实亚洲人健康肤色、"
    "蓝天白云、深蓝或黑色西装、白色衬衫、草木绿色、建筑物呈现灰白原色；"
    "色调均衡不过度偏黄偏棕，不要做旧泛黄的怀旧滤镜，颜色自然鲜艳")


def build_enhanced(
    photo_id: str,
    settings=None,
    refine=None,
    out_long_width: int = OUT_LONG_WIDTH,
) -> bool:
    """对单张照片跑两步云链，产出 data/processed/{pid}/enhanced.jpg。"""
    try:
        if refine is None:
            from app.ingest.cloud_refine import refine_image as refine
        root = Path("data/processed") / photo_id
        src = root / "restored.jpg"
        if not src.exists():
            logger.warning("enhance 缺 restored.jpg: %s", photo_id)
            return False

        tmp_in = root / ".enh-in.jpg"
        with Image.open(src) as im:
            im = im.convert("RGB")
            im.thumbnail((IN_LONG_SIDE, IN_LONG_SIDE), Image.LANCZOS)
            im.save(tmp_in, quality=92)

        ok_repair = refine(tmp_in, root / ".enh-repair.png",
                           function="description_edit",
                           prompt=REPAIR_PROMPT, settings=settings)
        if not ok_repair:
            return False
        ok_color = refine(root / ".enh-repair.png", root / ".enh-color.png",
                          function="colorization", prompt=COLOR_PROMPT,
                          settings=settings)
        if not ok_color:
            return False

        with Image.open(root / ".enh-color.png") as im2:
            im2 = im2.convert("RGB")
            w, h = im2.size
            tw = max(out_long_width, w)
            im_out = im2.resize((tw, int(h * tw / w)), Image.LANCZOS)
            im_out = im_out.filter(ImageFilter.UnsharpMask(
                radius=2.2, percent=85, threshold=3))
            dst = root / "enhanced.jpg"
            im_out.save(dst, quality=93)
        for t in (tmp_in, root / ".enh-repair.png", root / ".enh-color.png"):
            t.unlink(missing_ok=True)
        return True
    except Exception as exc:  # noqa: BLE001 —— 降级边界
        logger.warning("enhance 失败(%s): %s", photo_id, exc)
        return False
