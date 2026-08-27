"""叙事链编排器：photo → insight → story → narration → review(回炉≤1) → TTS。

把 4 个叙事 Agent（insight/story_writer/cantonese/reviewer）+ detox 校验
编排成一条主链路，带降级（degraded 标记）与幂等产物缓存。
CLI（T11）与 Web（T13）都调 run_story_chain。

降级铁律（AGENTS.md #4）：任何一环失败绝不上抛异常——
story 不合格 → fallback_docent；TTS 失败 → audio=False + degraded。
deps 注入 seam：缺省 _DefaultDeps 调真实模块；测试注入替身。
"""
import json
import logging
from pathlib import Path

from app.narrator.types import Story

logger = logging.getLogger(__name__)

_DEFAULT_EXTS = ("colorized.jpg", "restored.jpg")
_RAW_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def _find_base_img(out_root, raw_dir, photo_id) -> Path | None:
    d = Path(out_root) / photo_id
    for name in _DEFAULT_EXTS:
        p = d / name
        if p.exists():
            return p
    for ext in _RAW_EXTS:
        p = Path(raw_dir) / f"{photo_id}{ext}"
        if p.exists():
            return p
    return None


def _metadata_desc(row) -> str:
    if not row:
        return "一张岭南老照片"
    return "|".join(str(row.get(k) or "") for k in ("title", "year", "location", "caption"))


def _fallback_docent_story(meta_desc) -> Story:
    return Story(text=f"这是一张记载岭南记忆的老照片。{meta_desc}",
                 source="fallback_docent", degraded=True)


def _detox_validate(text, deps):
    """deps 提供 validate_story 则用之，否则 import 真实 detox。"""
    if hasattr(deps, "validate_story"):
        return deps.validate_story(text)
    from app.narrator import detox as dx
    return dx.validate_story(text)


class _DefaultDeps:
    """真实实现：调用各 agent 模块。"""

    @staticmethod
    def insight(base, meta, settings=None):
        from app.narrator import insight as m
        return m.insight(base, meta, settings=settings)

    @staticmethod
    def write_story(ins, settings=None, chat=None):
        from app.narrator import story_writer as m
        return m.write_story(ins, settings=settings, chat=chat)

    @staticmethod
    def write_narration(st, settings=None, chat=None):
        from app.narrator import cantonese as m
        return m.write_narration(st, settings=settings, chat=chat)

    @staticmethod
    def review(ins, st, settings=None, chat=None):
        from app.narrator import reviewer as m
        return m.review(ins, st, settings=settings, chat=chat)

    @staticmethod
    def tts(text, settings, out_path, voice=None):
        from app.infra.tts import get_tts
        s = settings or __import__("app.config", fromlist=["Settings"]).Settings.load()
        return get_tts(s).synthesize(text, voice or s.tts_voice, out_path)


def run_story_chain(photo_id, settings=None, force=False, deps=None,
                    out_root=None, raw_dir=None, row=None, voice=None) -> dict:
    deps = deps or _DefaultDeps
    s = settings or __import__("app.config", fromlist=["Settings"]).Settings.load()
    out_root = Path(out_root or "data/processed")
    raw_dir = Path(raw_dir or "data/raw")
    out_dir = out_root / photo_id
    out_dir.mkdir(parents=True, exist_ok=True)
    story_p, nar_p, wav_p = (out_dir / "story.json"), (out_dir / "narration.json"), (out_dir / "narration.wav")

    result = {"photo_id": photo_id, "degraded": False, "audio": False, "source": "llm"}

    # 幂等：三件产物齐且非 force → 直接返回缓存
    if not force and story_p.exists() and nar_p.exists() and wav_p.exists():
        result["story"] = json.loads(story_p.read_text(encoding="utf-8")).get("text", "")
        result["narration"] = nar_p.read_text(encoding="utf-8")
        result["audio"] = True
        return result

    meta_desc = _metadata_desc(row)
    base = _find_base_img(out_root, raw_dir, photo_id)

    ins = deps.insight(base, meta_desc, settings=s)
    st = deps.write_story(ins, settings=s, chat=None)
    if st.degraded or not _detox_validate(st.text, deps):
        st = _fallback_docent_story(meta_desc)
        result["source"] = "fallback_docent"
    result["story"] = st.text
    result["degraded"] = st.degraded or ins.degraded

    nar = deps.write_narration(st, settings=s, chat=None)
    lines = [{"text": ln.text, "emotion": ln.emotion} for ln in nar.lines]
    plain = "。".join(ln.text for ln in nar.lines)

    rv = deps.review(ins, st, settings=s, chat=None)
    max_retry = s.max_story_retry
    if rv.score < 85 and max_retry > 0:
        st2 = deps.write_story(ins, settings=s, chat=None)
        if not st2.degraded and _detox_validate(st2.text, deps):
            st = st2
            nar = deps.write_narration(st, settings=s, chat=None)
            lines = [{"text": ln.text, "emotion": ln.emotion} for ln in nar.lines]
            plain = "。".join(ln.text for ln in nar.lines)
            result["story"] = st.text
            result["source"] = "llm"
        result["degraded"] = result["degraded"] or (rv.score < 85)

    story_p.write_text(json.dumps({"text": result["story"]}, ensure_ascii=False, indent=2), encoding="utf-8")
    nar_p.write_text(json.dumps({"lines": lines}, ensure_ascii=False, indent=2), encoding="utf-8")

    try:
        ok = deps.tts(plain, s, wav_p, voice=voice)
        result["audio"] = bool(ok)
        result["degraded"] = result["degraded"] or not ok
    except Exception:  # noqa: BLE001 —— 降级边界，绝不抛出
        logger.warning("TTS 失败，隐藏音频", exc_info=True)
        result["audio"] = False
        result["degraded"] = True

    result["narration"] = nar_p.read_text(encoding="utf-8")
    return result