"""F7 Web 展馆：FastAPI + Jinja2 服务端渲染 + 原生前端（不上重型框架）。

页面：首页照片墙 / 详情(对比滑块) / 搜索 / 问答(SSE) / 专题展览。
降级语义：Milvus 未启动 → 页面横幅给中文提示与启动命令，不允许挂死。
"""
import json
import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.agents import creator, curator, docent, narrator
from app.infra import reranker as rr
from app.infra.tts import VOICES
from app.retrieval import pipeline as rpipe

logger = logging.getLogger(__name__)

_BASE = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(_BASE / "templates"))


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


def _settings():
    from app.config import Settings

    return Settings.load()


def _health_flags() -> dict[str, bool]:
    """外部依赖探活；任何异常按不可用处理，绝不让健康检查挂死。"""
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
    return flags


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
        return TEMPLATES.TemplateResponse(
            request, "detail.html",
            {"p": row, "pid": photo_id,
             "has_restored": (base / "restored.jpg").exists(),
             "has_colorized": bool(row.get("has_colorized"))
             and (base / "colorized.jpg").exists(),
             "has_narration": (base / "narration.wav").exists(),
             "has_video": (base / "narration.mp4").exists(),
             "voices": VOICES,
             "tts_voice": _settings().tts_voice},
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
        result = narrator.narrate(photo_id, voice=voice)
        if "error" in result:
            msg = result["error"]
            raise HTTPException(404 if "不存在" in msg else 502, msg)
        return result

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
