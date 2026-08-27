"""一次性对照实验：同一张图四种增强变体 + 比对页 HTML。

变体：
- base        现管线 colorized.jpg（基准）
- punch       Pillow 锐化+提饱和+微对比（零成本猛药）
- cf05        CodeFormatter 二次人脸修复(w=0.5, 局部更平滑)
- ccolor      万相按提示词自然上色（取代 DDColor 配色）
产物落 data/processed/{pid}/compare/；仅供人工审美决策，不改主产物。
"""
import io
import logging
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageEnhance

logging.basicConfig(level=logging.INFO, format="%(message)s")
PID = "gz_file1919jpg_006"
ROOT = Path("data/processed") / PID
OUT = ROOT / "compare"
OUT.mkdir(parents=True, exist_ok=True)

_VENDOR = Path("models/vendor")
_CF_PY = _VENDOR / "venv-cf/Scripts/python.exe"
_CF_REPO = _VENDOR / "CodeFormer"
_DD_REPO = _VENDOR / "DDColor"

status: dict[str, str] = {}


def _copy(src_name: str, dst_name: str):
    p = ROOT / src_name
    if p.exists():
        shutil.copy2(p, OUT / dst_name)
        return True
    return False


def punch():
    """锐化+饱和+微对比。"""
    im = Image.open(ROOT / "colorized.jpg").convert("RGB")
    im = ImageEnhance.Sharpness(im).enhance(1.8)
    im = ImageEnhance.Color(im).enhance(1.45)
    im = ImageEnhance.Contrast(im).enhance(1.08)
    im.save(OUT / "v-punch.jpg", quality=93)
    return True


def cf_second_pass():
    """在 3840 图上再跑一遍 CodeFormer(w=0.5)。"""
    out_dir = (OUT / ".tmp-cf").resolve()
    env_path_dd = str(_DD_REPO.resolve())
    import os

    env = dict(os.environ)
    env["PYTHONPATH"] = env_path_dd
    cmd = [str(_CF_PY.resolve()), str((_CF_REPO / "inference_codeformer.py").resolve()),
           "-w", "0.5", "-i", str((ROOT / "colorized.jpg").resolve()),
           "-o", str(out_dir), "--face_upsample"]
    proc = subprocess.run(cmd, cwd=str(_CF_REPO.resolve()), env=env,
                          capture_output=True, timeout=600)
    if proc.returncode != 0:
        logging.info("cf 二次修复失败: %s",
                     proc.stderr.decode('utf-8', 'ignore')[-200:])
        return False
    imgs = [p for p in out_dir.rglob("*")
            if p.suffix.lower() in (".png", ".jpg", ".jpeg")]
    if not imgs:
        return False
    best = max(imgs, key=lambda p: p.stat().st_size)
    Image.open(best).convert("RGB").save(OUT / "v-cf05.jpg", quality=93)
    shutil.rmtree(out_dir, ignore_errors=True)
    return True


def cloud_color():
    """万相提示词上色（输入先降采样满足接口限制）。"""
    from app.config import Settings
    from app.ingest.cloud_refine import refine_image

    im = Image.open(ROOT / "restored.jpg").convert("RGB")
    im.thumbnail((1440, 1440), Image.LANCZOS)
    tiny_in = ROOT / ".tmp-color-in.jpg"
    im.save(tiny_in, quality=88)
    ok = refine_image(
        tiny_in, OUT / "v-ccolor.jpg", function="colorization",
        prompt=("为这张1919年广东运动会历史老照片自然上色：晴天薄云的天空、"
                "深色西装配白衬衫礼帽、健康真实的亚洲人肤色、黄褐色草地、"
                "年代感自然色调，画面真实不鲜艳过度"),
        settings=Settings.load())
    tiny_in.unlink(missing_ok=True)
    return ok


def crops():
    """各变体同位置裁一块中央放大区（便于看人脸细节）。"""
    for name in ("v-base", "v-punch", "v-cf05", "v-ccolor"):
        p = OUT / f"{name}.jpg"
        if not p.exists():
            continue
        im = Image.open(p)
        w, h = im.size
        box = (int(w * 0.28), int(h * 0.04),
               int(w * 0.78), int(h * 0.60))          # 中央偏上人群区
        im.crop(box).save(OUT / f"{name}-crop.jpg", quality=90)


if __name__ == "__main__":
    if _copy("colorized.jpg", "v-base.jpg"):
        status["base"] = "OK"
    else:
        status["base"] = "NG 缺基准图"
    for name, fn in (("punch", punch), ("cf05", cf_second_pass),
                     ("ccolor", cloud_color)):
        try:
            status[name] = "OK" if fn() else "NG 失败降级"
        except Exception as exc:  # noqa: BLE001 —— 实验脚本允许宽捕获
            status[name] = f"NG {exc}"
    crops()
    for k, v in status.items():
        print(f"[{'OK' if v.startswith('OK') else 'NG'}] {k}: {v}")
