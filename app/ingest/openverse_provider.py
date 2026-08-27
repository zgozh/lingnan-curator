"""Openverse 公版图 Provider：cc0/pdm 白名单 → data/raw + meta 行。

Openverse 聚合多站点（Flickr/Wikimedia/博物馆）的 CC 图像，
匿名可查询（限速宽松）；license=pdm(Public Domain Mark)/cc0 才放行。
"""
import logging
import re
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_API = "https://api.openverse.org/v1/images/"
_MAX_BYTES = 20 * 1024 * 1024
_HEADERS = {"User-Agent": "lingnan-curator-bot/1.0 (competition demo)"}


def _pid_slug(title: str) -> str:
    slug = re.sub(r"[^0-9a-z]+", "_", (title or "").lower()).strip("_")[:40]
    return slug or "img"


def crawl_openverse(query: str, limit: int, location: str,
                    client: httpx.Client | None,
                    raw_dir: Path) -> list[dict]:
    """检索 Openverse 并下载公版图；返回 meta 行，单条失败降级为日志。"""
    own = client is None
    cli = client or httpx.Client(timeout=60, headers=_HEADERS)
    rows: list[dict] = []
    try:
        resp = cli.get(_API, params={
            "q": query, "page_size": min(limit * 2, 50),
            "license": "cc0,pdm"})
        items = (resp.json().get("results")) or []
        for it in items[:limit]:
            try:
                lic_raw = str(it.get("license") or "").lower()
                if lic_raw not in ("cc0", "pdm"):
                    logger.warning("[SKIP] %s: 许可 %s 不可用",
                                   it.get("title"), lic_raw)
                    continue
                url = it.get("url") or ""
                if not url.startswith(("http://", "https://")):
                    continue
                dl = cli.get(url)
                if dl.status_code != 200 or not dl.content \
                        or len(dl.content) > _MAX_BYTES:
                    logger.warning("[SKIP] %s: 下载失败/超限", it.get("title"))
                    continue
                title = re.sub(r"\.(jpe?g|png)$", "",
                               str(it.get("title") or "image"),
                               flags=re.I)
                pid = (f"ov_{_pid_slug(title)}_"
                       f"{int(time.time()) % 100000:05d}")
                ctype = dl.headers.get("content-type", "")
                ext = ".png" if "png" in ctype else ".jpg"
                out = Path(raw_dir) / f"{pid}{ext}"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(dl.content)
                license_label = ("Public domain (PDM)"
                                 if lic_raw == "pdm" else "CC0")
                rows.append({
                    "photo_id": pid,
                    "title": title.strip() or "Openverse image",
                    "year": "",           # Openverse 无统一年代字段
                    "location": location,
                    "source_url": (it.get("foreign_landing_url") or url),
                    "license": license_label,
                })
                print(f"[OK] {title} -> {out.name}")
            except Exception as exc:  # noqa: BLE001 单条失败不拖垮批次
                logger.warning("[NG] openverse 条目失败: %s", exc)
        return rows
    finally:
        if own:
            cli.close()
