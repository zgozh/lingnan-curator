"""F6 口播基座：TTSProvider 协议 + DashScope CosyVoice 粤语实现 + 可选 Edge-TTS Provider。

降级铁律：TTS 失败返回 False，上层隐藏口播入口（spec 边界案例），
绝不抛异常打断主链路。
"""
import io
import logging
import wave
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


def _concat_wav(chunks: list[bytes], out_path: Path) -> bool:
    """用 wave 模块把多个独立 WAV 正确拼成一个 WAV（保留头部参数，只拼接帧）。

    任一 chunk 无法作为 WAV 解析，或各段音频参数（声道/采样率/位宽）不一致时
    返回 False，由调用方回退到「整段文本单次合成」。
    """
    params = None
    frames: list[bytes] = []
    try:
        for chunk in chunks:
            with wave.open(io.BytesIO(chunk), "rb") as w:
                p = w.getparams()
                if params is None:
                    params = p
                elif (p.nchannels, p.framerate, p.sampwidth) != (
                    params.nchannels, params.framerate, params.sampwidth,
                ):
                    logger.warning("按句 TTS 各段 WAV 参数不一致，回退单次合成")
                    return False
                frames.append(w.readframes(w.getnframes()))
    except (wave.Error, EOFError, OSError, ValueError) as exc:
        logger.warning("按句 TTS 的 WAV 无法解析，回退单次合成: %s", exc)
        return False
    if params is None:
        return False
    with wave.open(str(out_path), "wb") as out:
        out.setnchannels(params.nchannels)
        out.setsampwidth(params.sampwidth)
        out.setframerate(params.framerate)
        out.writeframes(b"".join(frames))
    return True


def synthesize_lines(lines, out_path, settings: Settings | None = None) -> bool:
    """逐句合成并拼接为单个 WAV（正确 WAV 帧拼接）。

    - 空 lines / 无 dashscope key → 返回 False。
    - 逐句调用 `_new_synthesizer(_MODEL, s.tts_voice, _FMT).call(text)` 得到 WAV 字节。
    - 通过 `wave` 模块按帧拼接；任一失败回退为「整段文本单次合成」。
    - 任何失败均返回 False（降级：由上层隐藏口播入口），绝不抛出。
    """
    s = settings or Settings.load()
    if not s.dashscope_api_key or not lines:
        return False
    try:
        synth = _new_synthesizer(_MODEL, s.tts_voice, _FMT)
        chunks: list[bytes] = []
        texts: list[str] = []
        for ln in lines:
            text = str(ln.get("text") or "") if isinstance(ln, dict) else str(ln)
            text = text.strip()
            if not text:
                continue
            audio = synth.call(text)
            if audio:
                chunks.append(audio)
                texts.append(text)
        if not chunks:
            return False
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        if _concat_wav(chunks, out):
            return True
        # 回退：拼接全部文本，整段单次合成（沿用当前 provider 的 synthesize）
        return get_tts(s).synthesize(" ".join(texts), s.tts_voice, out)
    except Exception as exc:  # noqa: BLE001 —— 降级边界，绝不抛出
        logger.warning("按句 TTS 失败: %s", exc)
        return False


class EdgeTTSCosyvoice:
    """可选边缘 TTS（Edge-TTS 粤语），仅作 Provider 切换候选（ADR-0007 seam）。

    edge-tts 为懒加载可选依赖：import 失败 / 网络失败 / 任何异常 → 返回 False，
    绝不抛异常打断 import 或主链路。
    """

    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings.load()
        self._voice = "zh-HK-HiuGaaiNeural"  # 沉稳女声

    def synthesize(self, text: str, voice: str, out_path: Path | str) -> bool:
        if not text.strip():
            return False
        try:
            import asyncio
            import edge_tts  # 懒加载：未安装则抛 ImportError → False

            out = Path(out_path)
            out.parent.mkdir(parents=True, exist_ok=True)

            async def _run():
                tts_ = edge_tts.Communicate(text, voice or self._voice)
                with open(out, "wb") as f:
                    async for chunk in tts_.stream():
                        if chunk["type"] == "audio":
                            f.write(chunk["data"])

            asyncio.run(_run())
            return True
        except Exception as exc:  # noqa: BLE001 —— 降级边界，绝不抛出
            logger.warning("edge-tts 失败: %s", exc)
            return False


def get_tts(settings: Settings | None = None):
    """按配置选择 TTS Provider：`tts_provider=="edge"` → Edge，否则 DashScope。"""
    s = settings or Settings.load()
    if getattr(s, "tts_provider", "dashscope") == "edge":
        return EdgeTTSCosyvoice(s)
    return DashScopeCosyvoice(s)
