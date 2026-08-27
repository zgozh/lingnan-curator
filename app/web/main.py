"""F7 Web 展馆：FastAPI + Jinja2 服务端渲染 + 原生前端（不上重型框架）。

页面：首页照片墙 / 详情(对比滑块) / 搜索 / 问答(SSE) / 专题展览。
降级语义：Milvus 未启动 → 页面横幅给中文提示与启动命令，不允许挂死。
"""
import json
import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.agents import creator, curator, docent
from app.infra import reranker as rr
from app.infra.tts import VOICES
from app.narrator.story import run_story_chain
from app.retrieval import pipeline as rpipe

logger = logging.getLogger(__name__)

# 健康探活缓存：rerank 未启动时探活要 2s 超时，不能每次请求都重复联网探活。
_FLAGS_TTL = 30.0
_flags_cache: dict = {"t": 0.0, "v": {}}

# 中文标题 sidecar（titles-zh.json）缓存：按文件 mtime 失效。
_zh_cache: dict = {"mtime": None, "v": {}}

_BASE = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(_BASE / "templates"))


def _titles_zh() -> dict[str, str]:
    """读中文标题映射（mtime 变了才重新加载；缺失/损坏→空）。"""
    p = Path("data/processed/titles-zh.json")
    try:
        mt = p.stat().st_mtime
    except OSError:
        return {}
    if _zh_cache["v"] and _zh_cache["mtime"] == mt:
        return _zh_cache["v"]
    from app.ingest.title_zh import load_titles_zh

    v = load_titles_zh(p)
    _zh_cache.update(mtime=mt, v=v)
    return v


def _zh_title(pid: str, title: str = "") -> str:
    """模板用：优先中文短标题，缺失回退原档案名。"""
    return _titles_zh().get(str(pid or ""), "") or (title or "")


def _media_src(pid: str) -> str:
    """展示图优先级：增强图 > 上色 > 修复；缺则占位图。"""
    base = Path("data/processed") / str(pid or "")
    for name in ("enhanced.jpg", "colorized.jpg", "restored.jpg"):
        if (base / name).exists():
            return f"/media/{pid}/{name}"
    return "/static/placeholder.svg"


def _media_exists(pid: str, name: str) -> bool:
    return (Path("data/processed") / str(pid or "") /
            name).is_file()


# 经模块属性转发，留测试缝（monkeypatch 可替换实现）
TEMPLATES.env.globals["media_src"] = lambda pid: _media_src(pid)
TEMPLATES.env.globals["media_exists"] = lambda pid, name: (
    _media_exists(pid, name))
TEMPLATES.env.globals["zh_title"] = lambda *a, **k: _zh_title(*a, **k)


def _photos_all(settings=None) -> list[dict]:
    """seam：首页照片墙数据（Milvus 全量著录）。"""
    from app.infra.milvus_store import get_client

    s = settings or _settings()
    rows = get_client(s).query(
        collection_name=s.collection,
        filter='photo_id != ""',
        output_fields=["photo_id", "title", "year", "location",
                       "has_colorized"],
        limit=100,
    )
    return rows


def _get_photo(photo_id: str, settings=None) -> dict | None:
    from app.infra.milvus_store import get_client

    s = settings or _settings()
    rows = get_client(s).query(
        collection_name=s.collection,
        filter=f'photo_id == "{photo_id}"',
        output_fields=["photo_id", "title", "year", "location", "caption",
                       "ocr_text", "license", "source_url", "has_colorized"],
        limit=1,
    )
    return rows[0] if rows else None


def _read_story(base: Path) -> tuple[str, list]:
    """读已缓存的叙事产物（幂等缓存）：story.json + narration.json。

    只读、不触发 LLM（生成走 /api/narrate）；未生成返回空。
    任何解析失败按空处理，绝不打垮页面（降级铁律）。
    """
    story_text, narration_lines = "", []
    try:
        sp = base / "story.json"
        if sp.exists():
            story_text = json.loads(sp.read_text(encoding="utf-8")).get("text", "")
        np_ = base / "narration.json"
        if np_.exists():
            _narr = json.loads(np_.read_text(encoding="utf-8"))
            _lines = _narr.get("lines", [])
            narration_lines = _lines if isinstance(_lines, list) else []
    except Exception:  # noqa: BLE001
        story_text, narration_lines = "", []
    return story_text, narration_lines


def _settings():
    from app.config import Settings

    return Settings.load()


def _health_flags() -> dict[str, bool]:
    """外部依赖探活；任何异常按不可用处理，绝不让健康检查挂死。

    结果缓存 _FLAGS_TTL 秒：rerank 未启动时探活要 2s 超时，不能每请求都探。
    """
    now = time.monotonic()
    if _flags_cache["v"] and (now - _flags_cache["t"]) < _FLAGS_TTL:
        return dict(_flags_cache["v"])
    flags = {"milvus": False, "rerank": False}
    try:
        s = _settings()
        from app.infra.milvus_store import count_photos, get_client

        count_photos(get_client(s), s.collection)
        flags["milvus"] = True
    except Exception as exc:  # noqa: BLE001
        logger.warning("Milvus 探活失败: %s", exc)
    try:
        flags["rerank"] = rr.health(getattr(_settings(), "rerank_base_url",
                                            None))
    except Exception:  # noqa: BLE001
        pass
    _flags_cache["t"] = now
    _flags_cache["v"] = flags
    return dict(flags)


def create_app() -> FastAPI:
    app = FastAPI(title="湾区记忆·岭南非遗 AI 策展人")
    media = Path("data/processed").resolve()
    if media.exists():
        app.mount("/media", StaticFiles(directory=str(media)), name="media")
    static_dir = _BASE / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)),
                  name="static")

    @app.get("/", response_class=None)
    def index(request: Request):
        flags = _health_flags()
        photos: list[dict] = []
        if flags.get("milvus"):
            try:
                photos = _photos_all()
            except Exception as exc:  # noqa: BLE001 —— 查询失败按未连接处理
                logger.warning("首页取馆藏失败: %s", exc)
                photos, flags["milvus"] = [], False
        return TEMPLATES.TemplateResponse(
            request, "index.html",
            {"photos": photos, "flags": flags},
        )

    @app.get("/search")
    def search_page(request: Request, q: str = ""):
        hits, degraded = [], set()
        if q.strip():
            res = rpipe.search(q, top_k=12)
            hits = res.hits
            degraded = res.degraded
        return TEMPLATES.TemplateResponse(
            request, "search.html", {"q": q, "hits": hits,
                                     "degraded": sorted(degraded)},
        )

    @app.get("/photo/{photo_id}")
    def photo_page(request: Request, photo_id: str):
        row = _get_photo(photo_id)
        if row is None:
            raise HTTPException(404, "馆藏中不存在该照片")
        base = Path("data/processed") / photo_id
        # 只读缓存，不触发生成（生成走 /api/narrate 按钮）——保页面秒开。
        story_text, narration_lines = _read_story(base)
        return TEMPLATES.TemplateResponse(
            request, "detail.html",
            {"p": row, "pid": photo_id,
             "has_restored": (base / "restored.jpg").exists(),
             "has_colorized": bool(row.get("has_colorized"))
             and (base / "colorized.jpg").exists(),
             "has_narration": (base / "narration.wav").exists(),
             "has_video": (base / "narration.mp4").exists(),
             "voices": VOICES,
             "tts_voice": _settings().tts_voice,
             "story": story_text,
             "narration_lines": narration_lines},
        )

    @app.get("/exhibit")
    def exhibit_page(request: Request, theme: str = ""):
        result = curator.compose(theme) if theme.strip() else {
            "theme": "", "sections": [], "refused": True}
        return TEMPLATES.TemplateResponse(
            request, "exhibit.html", {"result": result},
        )

    @app.post("/api/ask")
    async def api_ask(request: Request):
        body = await request.json()
        q = str(body.get("q") or "").strip()
        if not q:
            raise HTTPException(400, "问题不能为空")

        def gen():
            for ev in docent.stream_answer(q):
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream")

    @app.post("/api/narrate/{photo_id}")
    def api_narrate(photo_id: str, body: dict):
        voice = str(body.get("voice") or "") or None
        if voice is not None and voice not in VOICES:
            raise HTTPException(400, f"不支持的音色: {voice}，"
                                     f"可选: {sorted(VOICES)}")
        chain = run_story_chain(photo_id, force=True, voice=voice)
        return {"audio": bool(chain.get("audio")),
                "degraded": bool(chain.get("degraded"))}

    @app.post("/api/create/{photo_id}")
    def api_create(photo_id: str, body: dict):
        copy_type = str(body.get("type") or "")
        try:
            return creator.create(photo_id, copy_type)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except LookupError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/api/health")
    def api_health():
        return _health_flags()

    return app


app = create_app()
