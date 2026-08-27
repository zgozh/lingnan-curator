"""抓取来源注册表：Commons（默认）+ Openverse，未知来源安全降级。

统一契约：run_source(name, query, limit, location, raw_dir)
        -> (rows: list[dict], logs: list[str])
来源实现自行负责下载文件到 raw_dir 并返回 meta 行（license 已过滤）。
"""
import logging
from pathlib import Path

import httpx

from app.ingest import commons_crawler
from app.ingest import openverse_provider as _ovp

logger = logging.getLogger(__name__)


def _crawl_commons(query: str, limit: int, location: str,
                   client: httpx.Client | None, raw_dir: Path) -> list[dict]:
    own = client is None
    cli = client or httpx.Client(timeout=60, headers=commons_crawler._HEADERS)
    try:
        return commons_crawler.crawl(query, limit, location, cli, raw_dir)
    finally:
        if own:
            cli.close()


def _crawl_openverse(query: str, limit: int, location: str,
                     client: httpx.Client | None, raw_dir: Path) -> list[dict]:
    return _ovp.crawl_openverse(query, limit, location, client, raw_dir)


# 用 lambda 惰性解析模块级函数，保证测试可替换缝（运行时才查找）
_SOURCES = {
    "commons": ("Wikimedia Commons 维基共享",
                lambda *a: _crawl_commons(*a)),
    "openverse": ("Openverse 聚合图库",
                  lambda *a: _crawl_openverse(*a)),
}


def run_source(name: str, query: str, limit: int, location: str,
               raw_dir: Path) -> tuple[list[dict], list[str]]:
    """按来源执行抓取；未知来源返回空行+日志，不抛异常。"""
    entry = _SOURCES.get(name)
    if entry is None:
        known = ", ".join(_SOURCES)
        return [], [f"[SKIP] 未知来源 {name}；可选：{known}"]
    label, func = entry
    logger.info("抓取来源 %s(%s)：query=%s limit=%s", name, label, query, limit)
    rows = func(query, limit, location, None, Path(raw_dir))
    return rows, []


def append_meta_rows(rows: list[dict],
                     meta_path: Path | None = None) -> list[str]:
    """把抓取行追加进 meta.csv（去重、自动表头）；返回最终生效的 pid 列表。"""
    import csv
    import uuid as _uuid

    path = Path(meta_path or "data/raw/meta.csv")
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ["photo_id", "title", "year", "location", "source_url",
              "license"]
    existing: set[str] = set()
    if path.exists():
        with open(path, encoding="utf-8-sig", newline="") as f:
            existing = {(r.get("photo_id") or "").strip()
                        for r in csv.DictReader(f)}
        need_header = False
    else:
        need_header = True
    final_pids: list[str] = []
    with open(path, "a", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        if need_header:
            writer.writeheader()
        for r in rows:
            while r["photo_id"] in existing:
                r["photo_id"] += "_" + _uuid.uuid4().hex[:4]
            writer.writerow({k: r.get(k, "") for k in header})
            existing.add(r["photo_id"])
            final_pids.append(r["photo_id"])
    return final_pids
