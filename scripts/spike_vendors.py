"""T7 spike 驱动：对指定 photo_id 实测 vendor 修复+上色。

用法：uv run python scripts/spike_vendors.py [photo_id]（默认 sample_b）
首次运行会下载权重（CodeFormer ~500MB + DDColor ~1GB），耗时属正常。
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 直跑时补项目根

from app.ingest.meta import find_image
from app.ingest.vision_ops import colorize, restore_face


def main() -> None:
    pid = sys.argv[1] if len(sys.argv) > 1 else "sample_b"
    raw = Path("data/raw")
    src = find_image(raw, pid)
    if src is None:
        raise SystemExit(f"[spike] {pid} 在 {raw} 找不到")

    out = Path("data/processed") / pid
    out.mkdir(parents=True, exist_ok=True)

    t0 = time.time()
    r1 = restore_face(src, out / "restored.jpg")
    t1 = time.time()
    r2 = colorize((out / "restored.jpg") if r1 else src, out / "colorized.jpg")
    t2 = time.time()
    print(f"[spike] {pid}: restore={r1}({t1 - t0:.0f}s) "
          f"colorize={r2}({t2 - t1:.0f}s)")
    for p in sorted(out.iterdir()):
        print(f"  - {p.name}  {p.stat().st_size:,}B")


if __name__ == "__main__":
    main()
