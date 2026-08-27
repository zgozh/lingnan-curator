"""画质增强 E2 链：云纯上色 + 亮度合成，产出 enhanced.jpg。

红线（v1 教训）：不做 description_edit 褶皱重绘——扩散重绘会幻改人脸，
历史照片保真不可妥协。本模块两段式：
1. restored 预缩 → 万相 colorization（自然色提示词）
2. YCbCr 合成：亮度 Y 完全取本地 restored 原图，色度 CbCr 取云端输出
   —— 结构数学上不可能变脸；褶皱保留但正常彩色后"脏感"自然减弱。

只新增 enhanced.jpg 副产物，绝不覆盖 restored/colorized 原始产物；
任何失败返回 False，展示层自动回退（降级铁律）。
"""
import logging
from pathlib import Path

from PIL import Image, ImageFilter

logger = logging.getLogger(__name__)

IN_LONG_SIDE = 1440        # 云端输入长边（接口限制内、保留可辨细节）
OUT_LONG_WIDTH = 3200      # 回贴目标宽（≥网页展示与明信片需求）

COLOR_PROMPT = (
    "为这张黑白老照片上自然真实的现代色彩：真实亚洲人健康肤色、"
    "蓝天白云、深蓝或黑色西装、白色衬衫、草木绿色、建筑物呈现灰白原色；"
    "色调均衡不过度偏黄偏棕，不要做旧泛黄的怀旧滤镜，颜色自然鲜艳")

PROMPT_SYSTEM = (
    "你是老照片上色的色彩指导。给你一张历史照片的AI著录描述，"
    "请输出一段中文上色提示词（80字内），只描述这张照片里该有的具体颜色："
    "天空/水面/建筑材质/衣物/肤色的合理自然色调。"
    "要求贴近史实、自然不鲜艳过度、明确避免整体泛黄泛棕。"
    '输出严格 JSON：{"prompt": "..."}')


def _composite(ref_rgb: Image.Image, cloud_rgb: Image.Image) -> Image.Image:
    """Y(结构/明暗)取 ref，CbCr(色彩)取 cloud。尺寸以 cloud 为准。"""
    if ref_rgb.size != cloud_rgb.size:
        ref_rgb = ref_rgb.resize(cloud_rgb.size, Image.LANCZOS)
    y = ref_rgb.convert("YCbCr").split()[0]
    cb, cr = cloud_rgb.convert("YCbCr").split()[1:]
    return Image.merge("YCbCr", (y, cb, cr)).convert("RGB")


def build_enhanced(
    photo_id: str,
    settings=None,
    refine=None,
    out_long_width: int = OUT_LONG_WIDTH,
) -> bool:
    """对单张照片跑 E2 链，产出 data/processed/{pid}/enhanced.jpg。"""
    try:
        if refine is None:
            from app.ingest.cloud_refine import refine_image as refine
        root = Path("data/processed") / photo_id
        src = root / "restored.jpg"
        if not src.exists():
            logger.warning("enhance 缺 restored.jpg: %s", photo_id)
            return False
        with Image.open(src) as base:
            ref_rgb = base.convert("RGB")

        tmp_in = root / ".enh-in.jpg"
        small = ref_rgb.copy()
        small.thumbnail((IN_LONG_SIDE, IN_LONG_SIDE), Image.LANCZOS)
        small.save(tmp_in, quality=92)

        ok_color = refine(tmp_in, root / ".enh-color.png",
                          function="colorization", prompt=COLOR_PROMPT,
                          settings=settings)
        tmp_in.unlink(missing_ok=True)
        if not ok_color:
            return False

        with Image.open(root / ".enh-color.png") as cloud:
            cloud_rgb = cloud.convert("RGB")
        comp = _composite(ref_rgb, cloud_rgb)
        w, h = comp.size
        tw = max(out_long_width, w)
        im_out = comp.resize((tw, int(h * tw / w)), Image.LANCZOS)
        im_out = im_out.filter(ImageFilter.UnsharpMask(
            radius=2.2, percent=80, threshold=3))
        dst = root / "enhanced.jpg"
        dst.parent.mkdir(parents=True, exist_ok=True)
        im_out.save(dst, quality=93)
        (root / ".enh-color.png").unlink(missing_ok=True)
        return True
    except Exception as exc:  # noqa: BLE001 —— 降级边界
        logger.warning("enhance 失败(%s): %s", photo_id, exc)
        return False


def tailor_prompt(row: dict, settings=None, chat=None) -> str:
    """caption/年代/地点 → 该照片专属上色提示词；失败返回空串。"""
    try:
        if chat is None:
            from app.infra import llm_client as lc

            chat = lc.chat
        s = settings or __import__("app.config",
                                    fromlist=["Settings"]).Settings.load()
        ctx = (f"标题：{row.get('title', '')}；年代：{row.get('year', '')}；"
               f"地点：{row.get('location', '')}；描述：{row.get('caption', '')}")
        raw = chat([{"role": "system", "content": PROMPT_SYSTEM},
                    {"role": "user", "content": ctx}],
                   json_mode=True, model=s.review_model, settings=s)
        from app.utils.json_utils import extract_json

        return str((extract_json(raw) or {}).get("prompt") or "").strip()
    except Exception as exc:  # noqa: BLE001 —— 降级边界
        logger.warning("tailor_prompt 失败: %s", exc)
        return ""


def build_candidate(
    photo_id: str,
    settings=None,
    row: dict | None = None,
    chat=None,
    refine=None,
    out_long_width: int = OUT_LONG_WIDTH,
) -> bool:
    """比稿候选：定制提示词 + E2 保脸链 → enhanced-archive/tailored-{pid}.jpg。

    只落存档区待人工评审，绝不直接顶替线上展示。失败返回 False。
    """
    try:
        if refine is None:
            from app.ingest.cloud_refine import refine_image as refine
        root = Path("data/processed") / photo_id
        src = root / "restored.jpg"
        if not src.exists():
            logger.warning("candidate 缺 restored.jpg: %s", photo_id)
            return False
        prompt = tailor_prompt(row or {}, settings=settings, chat=chat)
        if not prompt:
            return False
        archive = root / "enhanced-archive"
        with Image.open(src) as base:
            ref_rgb = base.convert("RGB")
        tmp_in = root / ".cand-in.jpg"
        small = ref_rgb.copy()
        small.thumbnail((IN_LONG_SIDE, IN_LONG_SIDE), Image.LANCZOS)
        small.save(tmp_in, quality=92)

        ok_color = refine(tmp_in, root / ".cand-color.png",
                          function="colorization", prompt=prompt,
                          settings=settings)
        tmp_in.unlink(missing_ok=True)
        if not ok_color:
            return False
        with Image.open(root / ".cand-color.png") as cloud:
            cloud_rgb = cloud.convert("RGB")
        comp = _composite(ref_rgb, cloud_rgb)
        w, h = comp.size
        tw = max(out_long_width, w)
        im_out = comp.resize((tw, int(h * tw / w)), Image.LANCZOS)
        im_out = im_out.filter(ImageFilter.UnsharpMask(
            radius=2.2, percent=80, threshold=3))
        archive.mkdir(parents=True, exist_ok=True)
        dest = archive / f"tailored-{photo_id}.jpg"
        im_out.save(dest, quality=93)
        (archive / f"tailored-{photo_id}.prompt.txt").write_text(
            prompt, encoding="utf-8")
        (root / ".cand-color.png").unlink(missing_ok=True)
        return True
    except Exception as exc:  # noqa: BLE001 —— 降级边界
        logger.warning("build_candidate 失败(%s): %s", photo_id, exc)
        return False
