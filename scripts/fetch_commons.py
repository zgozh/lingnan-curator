"""Wikimedia Commons 公有领域岭南老照片抓取器（版权红线自动化）。

用法（网络需可达 Commons，可挂代理）：
  uv run python scripts/fetch_commons.py \
      --category Historical_images_of_Guangzhou --limit 40 \
      --location 广州 [--proxy http://127.0.0.1:10809]

流程：分类成员 → imageinfo+extmetadata → 许可白名单(PD/CC0/CC BY/CC BY-SA，
拒 NC/ND) → 宽度≥min-width → 下载缩略图 JPG → data/raw/ + meta.csv 六列追加
（对已有 photo_id 幂等跳过）。
"""
import argparse
import csv
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data/raw"
META = RAW / "meta.csv"
_UA = {"User-Agent": "lingnan-curator/0.1 (student contest demo)"}
_API = "https://commons.wikimedia.org/w/api.php"
_META_FIELDS = ["photo_id", "title", "year", "location", "license",
                "source_url"]

_LICENSE_OK_RE = re.compile(r"public domain|cc0|cc by(?![^-]*-(?:nc|nd))",
                            re.I)
_LICENSE_BAD_RE = re.compile(r"-(?:nc|nd)|non-free|fair use|©|copyrighted",
                             re.I)


def _license_ok(name: str | None) -> bool:
    if not name:
        return False
    if _LICENSE_BAD_RE.search(name):
        return False
    return bool(_LICENSE_OK_RE.search(name))


def _year_from(text: str) -> str:
    m = re.search(r"(1[5-9]\d{2})", text or "")
    return m.group(1) if m else ""


def _slug(title: str, idx: int) -> str:
    base = re.sub(r"[^0-9a-zA-Z]+", "", title).lower()[:20] or "img"
    return f"gz_{base}_{idx:03d}"


def _existing_ids(csv_path: Path) -> set[str]:
    if not csv_path.exists():
        return set()
    with open(csv_path, encoding="utf-8-sig", newline="") as f:
        return {(r.get("photo_id") or "") for r in csv.DictReader(f)} - {""}


def _opener(proxy: str | None):
    if proxy:
        handler = urllib.request.ProxyHandler(
            {"http": proxy, "https": proxy})
        return urllib.request.build_opener(handler)
    return urllib.request.build_opener()


def _api(opener, **params) -> dict:
    url = _API + "?" + urllib.parse.urlencode({"format": "json", **params})
    req = urllib.request.Request(url, headers=_UA)
    with opener.open(req, timeout=90) as r:
        return json.loads(r.read().decode("utf-8"))


def _file_titles(opener, category: str, search: str, limit: int):
    """产出文件页标题；优先分类，其次全文搜索(namespace=6)。"""
    got = 0
    if category:
        cont: dict = {}
        while got < limit:
            data = _api(opener, action="query", list="categorymembers",
                        cmtitle=f"Category:{category}", cmtype="file",
                        cmlimit=min(limit - got, 50), **cont)
            for m in data.get("query", {}).get("categorymembers", []):
                yield m["title"]
                got += 1
            cont = {"cmcontinue": data["continue"]["cmcontinue"]} \
                if "continue" in data else {}
            if not cont:
                break
    if search:
        data = _api(opener, action="query", list="search",
                    srsearch=search, srnamespace=6,
                    srlimit=min(limit - got, 50))
        for m in data.get("query", {}).get("search", []):
            yield m["title"]
            got += 1


def _info(opener, title: str, out_width: int) -> dict | None:
    data = _api(opener, action="query", titles=title, prop="imageinfo",
                iiprop="url|size|extmetadata|mime", iiurlwidth=out_width)
    for page in data.get("query", {}).get("pages", {}).values():
        ii = (page.get("imageinfo") or [{}])[0]
        em = ii.get("extmetadata") or {}

        def _v(key: str) -> str:
            return str((em.get(key) or {}).get("value") or "")

        return {
            "title": title,
            "thumb": ii.get("thumburl") or "",
            "width": int(ii.get("width") or 0),
            "mime": ii.get("mime") or "",
            "license": (_v("LicenseShortName") or _v("License")),
            "date": _v("DateTimeOriginal"),
            "page": ("https://commons.wikimedia.org/wiki/"
                     + title.replace(" ", "_")),
        }
    return None


def _download(opener, url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers=_UA)
        with opener.open(req, timeout=180) as r, open(dest, "wb") as f:
            while chunk := r.read(1 << 20):
                f.write(chunk)
        return dest.stat().st_size > 10_000
    except Exception as exc:  # noqa: BLE001 —— 单张失败不拖垮批次
        print(f"  [dl-fail] {exc}")
        return False


def main(argv=None) -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--category", default="")
    ap.add_argument("--search", default="")
    ap.add_argument("--limit", type=int, default=30)
    ap.add_argument("--location", default="广州")
    ap.add_argument("--min-width", type=int, default=1200)
    ap.add_argument("--out-width", type=int, default=1600)
    ap.add_argument("--proxy", default="")
    args = ap.parse_args(argv)

    RAW.mkdir(parents=True, exist_ok=True)
    opener = _opener(args.proxy or None)
    existing = _existing_ids(META)
    new_meta: list[dict] = []
    idx = len(existing) + 1

    for title in _file_titles(opener, args.category, args.search,
                              args.limit * 3):
        if len(new_meta) >= args.limit:
            break
        info = _info(opener, title, args.out_width)
        if not info:
            continue
        if info["mime"] not in ("image/jpeg", "image/png"):
            continue
        if info["width"] < args.min_width:
            print(f"  [skip] 太窄 {info['width']}px: {title[:48]}")
            continue
        if not _license_ok(info["license"]):
            print(f"  [skip] 许可[{info['license'][:28]}]: {title[:40]}")
            continue

        slug = _slug(title, idx)
        dest = RAW / f"{slug}.jpg"
        if not _download(opener, info["thumb"], dest):
            continue
        idx += 1
        new_meta.append({
            "photo_id": slug,
            "title": re.sub(r"^File:", "", title),
            "year": _year_from(info["date"]),
            "location": args.location,
            "license": info["license"],
            "source_url": info["page"],
        })
        print(f"  [OK] {slug} <- {title[:52]}")

    if new_meta:
        exists = META.exists()
        fields = _META_FIELDS
        if exists:
            with open(META, encoding="utf-8-sig", newline="") as f:
                header = next(csv.reader(f), None)
            # 追加必须对齐现有表头列序，否则 DictWriter 会把值写串列
            if header and set(header) == set(_META_FIELDS):
                fields = header
        with open(META, "a", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields)
            if not exists:
                w.writeheader()
            w.writerows(new_meta)
    print(f"\n=== 新增 {len(new_meta)} 张，meta.csv 现有 "
          f"{len(_existing_ids(META))} 条 ===")


if __name__ == "__main__":
    main()
