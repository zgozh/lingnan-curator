"""探测 CosyVoice model×voice 可用组合。"""
import sys
import pathlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.infra import tts as tts_mod  # noqa: E402

COMBOS = [
    ("cosyvoice-v2", "longanyue"),
    ("cosyvoice-v2", "longjiayi_v2"),
    ("cosyvoice-v2", "longtao_v2"),
    ("cosyvoice-v2", "longjiaxin_v3"),
    ("cosyvoice-v3", "longjiaxin_v3"),
    ("cosyvoice-v3", "longanyue_v3"),
]


def main() -> None:
    text = "大家好，欢迎收听粤语讲解测试。"
    for model, voice in COMBOS:
        tts_mod._MODEL = model  # 探测期临时替换

        class _S:
            dashscope_api_key = "from-env"

        def new_synth(m, v, f):
            from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer

            return SpeechSynthesizer(model=m, voice=v,
                                     format=getattr(AudioFormat, f))
        tts_mod._new_synthesizer = new_synth
        prov = tts_mod.DashScopeCosyvoice()
        try:
            synth = new_synth(model, voice, tts_mod._FMT)
            audio = synth.call(text)
            print(f"{model} × {voice}: OK {len(audio):,}B")
        except Exception as exc:
            print(f"{model} × {voice}: FAIL {str(exc)[:90]}")
        _ = prov


if __name__ == "__main__":
    main()
