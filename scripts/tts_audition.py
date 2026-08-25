"""TTS 听测：生成两个粤语音色样音供拍板。

用法：uv run python scripts/tts_audition.py [photo_id]
产物：data/processed/<photo_id>/tts-<voice>.wav
"""
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.infra.tts import get_tts  # noqa: E402

TEXT = (
    "大家好，欢迎来到湾区记忆展馆。"
    "呢张相影住十九三十年代广州嘅骑楼街景，"
    "一楼嘅柱廊行人如鲫，楼上仲挂住老字号招牌，"
    "见证咗岭南商业文化最繁华嘅岁月。"
)

VOICES = ["longjiayi_v2", "longtao_v2", "longanyue"]
# 知性粤语女 / 积极粤语女 / 欢脱粤语男（cosyvoice-v2 实测可用组合）


def main() -> None:
    pid = sys.argv[1] if len(sys.argv) > 1 else "sample_a"
    tts = get_tts()
    for voice in VOICES:
        out = pathlib.Path("data/processed") / pid / f"tts-{voice}.wav"
        ok = tts.synthesize(TEXT, voice, out)
        size = out.stat().st_size if ok else 0
        print(f"{voice}: {'OK' if ok else 'FAIL'} {size:,}B -> {out}")


if __name__ == "__main__":
    main()
