"""F6 口播基座：TTSProvider 协议 + DashScope CosyVoice 粤语实现。

降级铁律：TTS 失败返回 False，上层隐藏口播入口（spec 边界案例），
绝不抛异常打断主链路。
"""
import logging
from pathlib import Path

from app.config import Settings

logger = logging.getLogger(__name__)

_MODEL = "cosyvoice-v2"
_FMT = "WAV_22050HZ_MONO_16BIT"

# 实测可用的 CosyVoice 粤语发音人（前端音色选择器数据源）
VOICES: dict[str, str] = {
    "longjiayi_v2": "知性粤语女",
    "longtao_v2": "积极粤语女",
    "longanyue": "欢脱粤语男",
}

def _new_synthesizer(model: str, voice: str, audio_format: str):
    """seam：测试替换；真实实现延迟 import（无 SDK/无 key 不炸 import）。"""
    from dashscope.audio.tts_v2 import AudioFormat, SpeechSynthesizer

    fmt = getattr(AudioFormat, audio_format)
    return SpeechSynthesizer(model=model, voice=voice, format=fmt)


class DashScopeCosyvoice:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.load()

    def synthesize(self, text: str, voice: str, out_path: Path | str) -> bool:
        if not self.settings.dashscope_api_key or not text.strip():
            return False
        try:
            synth = _new_synthesizer(_MODEL, voice, _FMT)
            audio = synth.call(text.strip())
            if not audio:
                logger.warning("TTS 返回空音频 voice=%s", voice)
                return False
            out = Path(out_path)
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(audio)
            return True
        except Exception as exc:  # noqa: BLE001 —— 降级边界，绝不抛出
            logger.warning("TTS 合成失败(将隐藏口播入口): %s", exc)
            return False


def get_tts(settings: Settings | None = None) -> DashScopeCosyvoice:
    return DashScopeCosyvoice(settings)
