"""Wikimedia Commons 爬虫：按关键词抓公版老照片 → data/raw + meta 行。

版权红线落地：只接受 LicenseShortName 含 "Public domain" 或 "CC0" 的文件，
其余一律跳过；source_url 指向 Commons 文件页（著录可溯源）。

用法：uv run python -m app.cli crawl --query "Guangzhou 1930" --limit 10
产出：图片存 data/raw/{pid}.jpg，返回 meta 行由 CLI 统一追加。
"""
import logging
import re
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_API = "https://commons.wikimedia.org/w/api.php"
_FREE_HINTS = ("public domain", "pd", "cc0")
_ALLOWED_EXT = (".jpg", ".jpeg", ".png")
_MAX_BYTES = 20 * 1024 * 1024
# Wikimedia 机器人政策要求规范 UA（带项目描述+联系方式），否则 403
_HEADERS = {
    "User-Agent": "lingnan-curator-bot/1.0 "
                  "(https://github.com/lingnan-curator; "
                  "contact curator@example.org) httpx",
    "Api-User-Agent": "lingnan-curator-bot/1.0 "
                      "(competition demo; contact curator@example.org)",
}


def _pid_slug(title: str) -> str:
    slug = re.sub(r"[^0-9a-z]+", "_",
                  title.replace("File:", "").lower()).strip("_")[:40]
    return slug or "img"


def _year_of(extmeta: dict) -> str:
    raw = (extmeta.get("DateTimeOriginal") or {}).get("value", "")
    m = re.search(r"(1[89]\d{2}|20[01]\d)", str(raw))
    return m.group(1) if m else ""


def _desc_of(extmeta: dict) -> str:
    raw = (extmeta.get("ImageDescription") or {}).get("value", "") or ""
    return re.sub(r"<[^>]+>", "", str(raw)).strip()[:300]


def _license_ok(lic: str) -> bool:
    low = (lic or "").lower()
    return any(h in low for h in _FREE_HINTS)


def crawl(query: str, limit: int, location: str, client: httpx.Client | None,
          raw_dir: Path) -> list[dict]:
    """检索并下载公版图；返回可追加进 meta.csv 的行。任何网络异常按条降级。"""
    own = client is None
    cli = client or httpx.Client(timeout=60, headers=_HEADERS)
    rows: list[dict] = []
    try:
        sr = cli.get(_API, params={
            "action": "query", "format": "json", "list": "search",
            "srnamespace": 6, "srlimit": limit * 3,
            "srsearch": f"{query} filetype:bitmap"})
        titles = [it["title"] for it in
                  (sr.json().get("query") or {}).get("search", [])
                  if str(it.get("title", "")).lower().endswith(_ALLOWED_EXT)]
        for t in titles[:limit]:
            try:
                ii = cli.get(_API, params={
                    "action": "query", "format": "json", "titles": t,
                    "prop": "imageinfo", "iiprop": "url|extmetadata|size",
                }).json()
                pages = ((ii.get("query") or {}).get("pages")) or {}
                info = None
                for page in pages.values():
                    arr = page.get("imageinfo") or []
                    if arr:
                        info = arr[0]
                        break
                if not info:
                    logger.warning("[SKIP] %s: 无 imageinfo", t)
                    continue
                extmeta = info.get("extmetadata") or {}
                lic = (extmeta.get("LicenseShortName") or {}).get(
                    "value", "")
                if not _license_ok(lic):
                    logger.warning("[SKIP] %s: 许可不可用(%s)，版权红线跳过",
                                   t, lic)
                    continue
                dl = cli.get(info["url"])
                if dl.status_code != 200 or len(dl.content) > _MAX_BYTES \
                        or not dl.content:
                    logger.warning("[SKIP] %s: 下载失败/超限", t)
                    continue
                slug = _pid_slug(t)
                pid = f"commons_{slug}_{int(time.time()) % 100000:05d}"
                ext = Path(info["url"]).suffix.lower() or ".jpg"
                if ext not in _ALLOWED_EXT:
                    ext = ".jpg" if "jpeg" not in (
                        (info.get("url") or "").lower()) else ".jpg"
                out = Path(raw_dir) / f"{pid}{ext}"
                out.parent.mkdir(parents=True, exist_ok=True)
                out.write_bytes(dl.content)
                rows.append({
                    "photo_id": pid,
                    "title": re.sub(r"\.[a-z]+$", "", t.replace("File:", "")),
                    "year": _year_of(extmeta),
                    "location": location,
                    "source_url": info.get("descriptionurl")
                                  or "https://commons.wikimedia.org/wiki/"
                                     + t.replace(" ", "_"),
                    "license": lic,
                })
                print(f"[OK] {t} -> {out.name}")
            except Exception as exc:  # noqa: BLE001 —— 单条失败不拖垮批次
                logger.warning("[NG] %s: %s", t, exc)
        return rows
    finally:
        if own:
            cli.close()
