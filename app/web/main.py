"""F7 Web 展馆：FastAPI + Jinja2 服务端渲染 + 原生前端（不上重型框架）。

页面：首页照片墙 / 详情(对比滑块) / 搜索 / 问答(SSE) / 专题展览。
降级语义：Milvus 未启动 → 页面横幅给中文提示与启动命令，不允许挂死。
"""
import json
import logging
import re as _re
import time
from io import BytesIO
from pathlib import Path

from fastapi import (FastAPI, File, Form, HTTPException, Request,
                     UploadFile)
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


def _review_rows() -> list[dict]:
    """比稿评审数据：每张照片的线上图 + 存档候选列表。Milvus 挂则空表。"""
    try:
        photos = _photos_all()
    except Exception as exc:  # noqa: BLE001 —— 降级边界
        logger.warning("评审页取著录失败: %s", exc)
        return []
    rows: list[dict] = []
    zh = _titles_zh()
    for p in photos:
        pid = str(p.get("photo_id") or "")
        if not pid or "/" in pid:
            continue
        d = Path("data/processed") / pid
        arch = d / "enhanced-archive"
        cands: list[dict] = []
        if arch.is_dir():
            for f in sorted(arch.iterdir()):
                if f.is_file() and f.suffix.lower() in (".jpg", ".jpeg",
                                                        ".png"):
                    cands.append({"name": f.name,
                                  "src": f"/media/{pid}/enhanced-archive/"
                                         f"{f.name}"})
        rows.append({
            "photo_id": pid,
            "zh_title": zh.get(pid) or p.get("title") or pid,
            "live": _media_src(pid),
            "has_live": (d / "enhanced.jpg").is_file(),
            "colorized_src": "/media/" + pid + "/colorized.jpg"
                             if (d / "colorized.jpg").is_file() else None,
            "candidates": cands,
            "prompt": (arch / f"tailored-{pid}.prompt.txt").read_text(
                encoding="utf-8")[:120]
            if (arch / f"tailored-{pid}.prompt.txt").is_file() else "",
        })
    return rows


_ALLOWED_CAND = {".jpg", ".jpeg", ".png"}


def _safe_archive_path(photo_id: str, file_name: str) -> Path | None:
    """评审文件路径安全：pid 与文件名都必须是纯 basename 且扩展名白名单。"""
    if not photo_id or not file_name:
        return None
    if "/" in photo_id or "\\" in photo_id or "." in photo_id:
        return None                      # pid 不允许带点/斜杠
    if "/" in file_name or "\\" in file_name or file_name.startswith("."):
        return None
    p = Path("data/processed") / photo_id / "enhanced-archive" / file_name
    if p.suffix.lower() not in _ALLOWED_CAND or p.parent.name != \
            "enhanced-archive":
        return None
    return p


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


def _spawn_ingest(photo_id: str) -> None:
    """后台子进程跑单张入库管线（不阻塞请求，日志落 data/logs）。"""
    _spawn_ingest_batch([photo_id])


def _spawn_ingest_batch(pids: list[str]) -> None:
    """一个子进程顺序入库多张（避免多进程挤爆 GPU），日志落 data/logs。"""
    import subprocess
    import sys

    log_dir = Path("data/logs")
    log_dir.mkdir(parents=True, exist_ok=True)
    log = open(log_dir / f"ingest-{'_'.join(pids[:3])}.log",
               "w", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, "-m", "app.cli", "ingest", "--pid",
         ",".join(pids)],
        stdout=log, stderr=subprocess.STDOUT, cwd=Path.cwd(),
    )


# 抓取任务注册表（单用户 demo：进程内 dict 足够；超量淘汰最旧）
_CRAWL_JOBS: dict[str, dict] = {}
_CRAWL_LOCK = None


def _crawl_worker(job_id: str, args: dict) -> None:
    from app.ingest.sources import append_meta_rows, run_source

    job = _CRAWL_JOBS[job_id]
    try:
        rows, logs = run_source(args["source"], args["query"],
                                args["limit"], args["location"],
                                Path("data/raw"))
        if rows:
            # append 可能为撞名加了后缀，按顺序回写最终 pid 供前端引用
            final = append_meta_rows(rows)
            for r, p in zip(rows, final):
                r["photo_id"] = p
        job.update(done=True, ok=True, rows=rows, logs=logs,
                   added=len(rows))
    except Exception as exc:  # noqa: BLE001 —— 任务失败不得打垮服务
        logger.warning("crawl job %s 失败: %s", job_id, exc)
        job.update(done=True, ok=False, rows=[], logs=[str(exc)],
                   added=0)


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

    @app.get("/review")
    def review_page(request: Request):
        """比稿评审页：逐张对比并决定启用哪一版上色（人工否决权）。"""
        return TEMPLATES.TemplateResponse(
            request, "review.html", {"rows": _review_rows()},
        )

    @app.post("/api/review/{photo_id}/enable")
    def review_enable(photo_id: str, body: dict):
        file_name = body.get("file")
        if not isinstance(file_name, str):
            raise HTTPException(400, "缺少候选文件名")
        cand = _safe_archive_path(photo_id, file_name)
        if cand is None or not cand.is_file():
            raise HTTPException(400, "非法或不存在候选文件")
        d = Path("data/processed") / photo_id
        live = d / "enhanced.jpg"
        archive = d / "enhanced-archive"
        import time as _t

        if live.exists():                     # 旧线上图先挪入存档保留
            stamp = _t.strftime("%Y%m%d-%H%M%S")
            live.rename(archive / f"replaced-{stamp}-{file_name}")
        cand.rename(live)                     # 移动语义：候选离场、转正上线
        return {"ok": True, "live": f"/media/{photo_id}/enhanced.jpg"}

    @app.post("/api/review/{photo_id}/withdraw")
    def review_withdraw(photo_id: str, body: dict):
        if (not photo_id or "/" in photo_id or "\\" in photo_id
                or "." in photo_id):
            raise HTTPException(400, "非法 photo_id")
        d = Path("data/processed") / photo_id
        live = d / "enhanced.jpg"
        if not live.is_file():
            raise HTTPException(404, "该照片当前没有启用增强图")
        archive = d / "enhanced-archive"
        import time as _t

        stamp = _t.strftime("%Y%m%d-%H%M%S")
        archive.mkdir(parents=True, exist_ok=True)
        live.rename(archive / f"withdrawn-{stamp}-enhanced.jpg")
        return {"ok": True}

    # ---------- 上传通道（数据输入） ----------
    _ALLOWED_EXT = {".jpg", ".jpeg", ".png"}
    _META_PATH = Path("data/raw/meta.csv")
    _RAW_DIR = Path("data/raw")

    @app.get("/upload")
    def upload_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "upload.html", {})

    def _append_meta(row: dict) -> None:
        """追加一行著录；文件缺失时自动补表头；pid 撞车自动加后缀去重。"""
        import csv
        import uuid as _uuid

        _META_PATH.parent.mkdir(parents=True, exist_ok=True)
        header = ["photo_id", "title", "year", "location",
                  "source_url", "license"]
        existing_pids: set[str] = set()
        if _META_PATH.exists():
            try:
                with open(_META_PATH, encoding="utf-8-sig", newline="") as f:
                    existing_pids = {(r.get("photo_id") or "").strip()
                                     for r in csv.DictReader(f)}
            except Exception:  # noqa: BLE001
                pass
        while row["photo_id"] in existing_pids:
            row["photo_id"] += "_" + _uuid.uuid4().hex[:4]
        with open(_META_PATH, "a", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=header)
            if not existing_pids:
                writer.writeheader()
            writer.writerow(row)

    @app.post("/api/upload")
    async def api_upload(
        title: str = Form(""),
        year: str = Form(""),
        location: str = Form(""),
        license: str = Form(""),
        source_url: str = Form(""),
        file: UploadFile | None = File(None),
    ):
        """版权红线：title/license/source_url 必填；仅 jpg/png；自动 pid。"""
        import uuid

        if file is None or not (file.filename or "").strip():
            raise HTTPException(400, "缺少图片文件")
        ext = Path(file.filename).suffix.lower()
        if ext not in _ALLOWED_EXT:
            raise HTTPException(400, "仅支持 jpg/jpeg/png 文件")
        title = title.strip()
        license_ = license.strip()
        source_url = source_url.strip()
        if not title:
            raise HTTPException(400, "标题必填")
        if not license_:
            raise HTTPException(
                400, "许可协议(License)必填——版权红线，缺者拒绝入库")
        if not source_url.startswith(("http://", "https://")):
            raise HTTPException(
                400, "来源链接(source_url)必填且须为 http(s) 地址")

        from PIL import Image as PILImage

        raw_bytes = await file.read()
        if len(raw_bytes) > 20 * 1024 * 1024:
            raise HTTPException(400, "图片超过 20MB 上限")
        try:
            img = PILImage.open(BytesIO(raw_bytes))
            if (img.format or "").upper() not in ("JPEG", "PNG"):
                raise ValueError(f"格式 {img.format} 不支持")
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(400, f"不是有效的 JPG/PNG 图片：{exc}") from exc

        slug = _re.sub(r"[^0-9a-zA-Z]+", "_", title).strip("_").lower()[:24]
        if not slug:
            slug = "photo"
        photo_id = f"user_{slug}_{uuid.uuid4().hex[:6]}"
        dest = _RAW_DIR / f"{photo_id}{ext}"
        _RAW_DIR.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(raw_bytes)
        _append_meta({
            "photo_id": photo_id, "title": title,
            "year": year.strip(), "location": location.strip(),
            "source_url": source_url, "license": license_,
        })
        _spawn_ingest(photo_id)
        return {"ok": True, "photo_id": photo_id,
                "status_url": f"/api/store-status/{photo_id}"}

    @app.get("/api/store-status/{photo_id}")
    def store_status(photo_id: str):
        """轮询：该照片是否已入库 Milvus（可出现在照片墙）。"""
        if "/" in photo_id or "\\" in photo_id or "." in photo_id:
            raise HTTPException(400, "非法 photo_id")
        return {"stored": _get_photo(photo_id) is not None}

    # ---------- 批量抓取（多来源） ----------
    import threading
    import uuid as _uuid

    @app.get("/crawl")
    def crawl_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "crawl.html", {})

    @app.post("/api/crawl")
    async def api_crawl(request: Request):
        body = await request.json()
        query = str(body.get("query") or "").strip()
        if not query:
            raise HTTPException(400, "缺少检索词")
        source = body.get("source") or "commons"
        limit = min(max(int(body.get("limit") or 5), 1), 12)
        location = str(body.get("location") or "").strip()[:24]
        job_id = _uuid.uuid4().hex[:8]
        while len(_CRAWL_JOBS) > 20:
            _CRAWL_JOBS.pop(next(iter(_CRAWL_JOBS)))
        _CRAWL_JOBS[job_id] = {"done": False, "ok": False, "rows": [],
                               "logs": [], "added": 0}
        threading.Thread(target=_crawl_worker, daemon=True,
                         args=(job_id, {"source": source, "query": query,
                                        "limit": limit,
                                        "location": location})).start()
        return {"ok": True, "job_id": job_id}

    @app.get("/api/crawl/status/{job_id}")
    def api_crawl_status(job_id: str):
        job = _CRAWL_JOBS.get(job_id)
        if not job:
            raise HTTPException(404, "任务不存在或已被清理")
        return job

    @app.post("/api/ingest-batch")
    def api_ingest_batch(body: dict):
        pids = [str(p) for p in (body.get("pids") or [])]
        ok, rejected = [], []
        for p in pids:
            if _re.fullmatch(r"[A-Za-z0-9_\-]+", p):
                ok.append(p)
            else:
                rejected.append(p)
        if not ok:
            raise HTTPException(400, "没有合法的 photo_id 可入库")
        _spawn_ingest_batch(ok)
        return {"ok": True, "queued": ok, "rejected": rejected}

    @app.get("/ask")
    def ask_page(request: Request):
        return TEMPLATES.TemplateResponse(request, "ask.html", {})

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
