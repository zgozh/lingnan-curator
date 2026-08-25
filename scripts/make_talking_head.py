"""口播视频生成：photo_id → (讲解词→TTS 音频) → SadTalker 口型视频。

用法（主 venv）：
  uv run python scripts/make_talking_head.py --pid sample_a [--no-tts]
产物：data/processed/<pid>/narration.wav（复用）+ narration.mp4
降级：任一步失败退出非零，上层按「隐藏口播入口」处理。
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ST_PY = ROOT / "models/vendor/venv-st/Scripts/python.exe"
SADTALKER = ROOT / "models/vendor/SadTalker"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", required=True)
    ap.add_argument("--no-tts", action="store_true",
                    help="跳过 TTS，直接用已有 narration.wav")
    args = ap.parse_args()

    out_dir = ROOT / "data/processed" / args.pid
    wav = out_dir / "narration.wav"
    img = out_dir / "restored.jpg"

    if not args.no_tts:
        r = subprocess.run([sys.executable, "-m", "app.cli", "narrate",
                            "--pid", args.pid], cwd=ROOT)
        if r.returncode != 0 or not wav.exists():
            raise SystemExit("TTS 阶段失败")
    elif not wav.exists():
        raise SystemExit("narration.wav 不存在且未允许生成")

    if not img.exists():
        raise SystemExit(f"缺少底图 {img}")

    result_dir = SADTALKER / "results"
    cmd = [str(ST_PY), "inference.py",
           "--driven_audio", str(wav),
           "--source_image", str(img),
           "--result_dir", str(result_dir),
           "--still", "--preprocess", "full"]

    # SadTalker 的 save_video_with_watermark 用裸 `ffmpeg` 命令混流；
    # 系统未装 ffmpeg 时借用 st venv 里 imageio-ffmpeg 的静态二进制。
    # 注意：其文件名带版本号(ffmpeg-win64-*.exe)，需复制为 ffmpeg.exe 垫片。
    env: dict[str, str] | None = None
    try:
        probe = subprocess.run(
            [str(ST_PY), "-c", "import imageio_ffmpeg;"
                               "print(imageio_ffmpeg.get_ffmpeg_exe())"],
            capture_output=True, text=True, check=True)
        ff_exe = Path(probe.stdout.strip().splitlines()[-1])
        shim_dir = SADTALKER / "ffmpeg_shim"
        shim_dir.mkdir(exist_ok=True)
        shim = shim_dir / "ffmpeg.exe"
        if not shim.exists():
            shutil.copyfile(ff_exe, shim)
        env = {**os.environ,
               "PATH": str(shim_dir) + os.pathsep + os.environ.get("PATH", "")}
        print("[ffmpeg-borrow]", shim)
    except Exception as exc:  # noqa: BLE001 —— 拿不到就按原样跑
        print("[ffmpeg-borrow] skip:", exc)

    print("[sadtalker]", " ".join(cmd))
    r = subprocess.run(cmd, cwd=SADTALKER, env=env)
    if r.returncode != 0:
        raise SystemExit("SadTalker 推理失败")

    vids = sorted(result_dir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime)
    if not vids:
        raise SystemExit("未找到输出 mp4")
    dest = out_dir / "narration.mp4"
    shutil.copy2(vids[-1], dest)
    print(f"[OK] {dest} ({dest.stat().st_size / 1e6:.1f}MB)")


if __name__ == "__main__":
    main()
